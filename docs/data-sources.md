# Data sources

PsiDataViz reads data from **public** locations with **no account and no API key**. You give it a public
link; it lists the files, groups them into datasets, and parses them on demand.

## Where to host data for PsiDataViz

> **TL;DR — use GitHub, Google Drive, Codeberg, or Box.** These let PsiDataViz list and read your files
> from a plain public link, no credentials.
>
> **Avoid Dropbox and Proton Drive for data you want to open in PsiDataViz.** They have no workable
> keyless path: a public **Dropbox** folder only offers a single whole-folder zip download (often
> hundreds of MB) and gates per-file listing behind a private, CSRF-protected API; **Proton Drive** is
> end-to-end encrypted, so even a password-less public link requires an SRP handshake plus client-side
> OpenPGP decryption that a server can't do. You can still *store* data there, but PsiDataViz can't scan
> it — so host (or mirror) anything you want others to open in the app on one of the four supported
> services above. See [Planned](#planned) for the technical detail.

| Host | Keyless scan | Good for |
| --- | --- | --- |
| **GitHub** / **Codeberg** | ✅ | versioned datasets, instrument- or sample-organized repos |
| **Google Drive** | ✅ | quick "Anyone with the link" folder sharing |
| **Box** | ✅ | shared folders (sample/compound layout) |
| Dropbox | ❌ | *not scannable* — don't rely on it for PsiDataViz |
| Proton Drive | ❌ | *not scannable* (E2E-encrypted) — don't rely on it for PsiDataViz |

## Supported today

### GitHub repositories

Paste a repo URL or `owner/repo`. Two cheap REST calls (resolve the default branch, then one recursive
git-tree listing) enumerate every file; contents are fetched lazily from `raw.githubusercontent.com`.
Setting a read-only `GITHUB_TOKEN` raises the API rate limit but is optional.

### Google Drive folders (keyless)

Share a folder as **"Anyone with the link"** and paste its URL. PsiDataViz walks the folder's
`embeddedfolderview` HTML — no Drive API key required — recursing into sub-folders (concurrently) and
downloading file bytes from `uc?export=download`. The large-file virus-scan interstitial is handled
automatically.

**How to share a Drive folder:**
1. Right-click the folder → **Share**.
2. Under *General access*, choose **Anyone with the link**.
3. Copy the link and paste it into PsiDataViz.

### Box shared folders (keyless)

Share a folder as **"Anyone with the link"** and paste its `app.box.com/s/…` URL. PsiDataViz reads the
`Box.postStreamData` JSON each folder page embeds (no Box API token), recurses through sub-folders, and
downloads file bytes from the keyless `index.php?rm=box_download_shared_file` endpoint.

## Planned

- **Dropbox** and **Proton Drive** public shares (tracked in
  [#4](https://github.com/jyarger/PsiDataViz/issues/4)). *Dropbox:* a public folder only exposes a
  whole-folder `?dl=1` **zip** (the example folder is ~700 MB — too heavy to scan), and per-file listing
  needs Dropbox's CSRF-gated internal API; a clean keyless path is still being investigated. *Proton Drive:*
  even a password-less public link requires a custom **SRP-6a handshake** (`/api/drive/urls/<token>/info`
  returns the SRP `Modulus`/`ServerEphemeral`/salt) plus **OpenPGP** decryption of the folder tree and file
  blocks — the `#fragment` is the client-side key, never sent to the server. Feasible but the most complex
  connector (mature implementations are Go-only); deferred since the same data is on Box/Codeberg/Drive.
- Provider buttons in the connect-helper; generalist research repositories (Zenodo, Figshare, Dryad,
  OSF, Mendeley Data); drag-and-drop and private/authenticated sources.

`make_source(url)` routes a URL to the right connector, and every connector implements the same
`DataSource` interface, so the catalog, app, and conversions work identically across sources.

## Example data (the PsiData collection)

The Yarger Lab publishes the same example data in several public locations:

| Location | Organized by | Status |
| --- | --- | --- |
| [GitHub `yargerlab/Data`](https://github.com/yargerlab/Data) | technique | ✅ supported |
| [Google Drive `Psi_Data`](https://drive.google.com/drive/folders/16VQhcRbCHkzhH2cq8T5DwyhTUBj2BrO4) | technique | ✅ supported |
| Proton Drive | technique | planned (E2E-encrypted) |
| Dropbox | sample / compound | planned |
| [Box `PsiData`](https://app.box.com/s/yigbg0fd5xj5n1hkxf8rcsemrkz7qgsx) | sample / compound | ✅ supported |
| [Codeberg `jyarger/PsiData`](https://codeberg.org/jyarger/PsiData) | sample / compound | ✅ supported |

The *technique*-organized sources have top-level folders per instrument (`DSC/`, `NMR/`, …); the
*sample*-organized ones have a folder per compound (`Aspirin/`, `CBD/`, …) — see
[the roadmap](ROADMAP.md)'s sample-centric phase.

## From files to datasets

Scanning is **metadata-only** (no downloads). For each discovered file:

1. **Group by base name.** Files that share a stem across extensions become one **`DataRecord`** with
   several **format variants** — e.g. `…_DSC.csv` + `…_DSC.tri` + `…_DSC.xls` is *one* dataset available
   in three formats. Variants are classified as data, binary-original, spreadsheet, sidecar, or image.
2. **Assign a technique.** Taken from the top-level folder and normalized to a canonical label
   (`canonical_technique()` maps `IR`/`FT-IR`/`infrared` → `FTIR`, `UV_Vis` → `UV-Vis`, …) so the same
   technique from different sources merges into one group.
3. **Flag support.** A record is `supported` when a registered reader is likely to handle it. Opening it
   later fetches the bytes and fully parses them.

## Two ways labs organize data

PsiDataViz handles both — and aims to unify them:

- **By instrument / technique** — top-level folders like `DSC/`, `NMR/`, `FTIR/`, `Raman/` (how the
  example GitHub repo and Google Drive folder are arranged).
- **By sample / compound** — top-level folders named for the chemical (`Aspirin/`, `CBD/`, …), each
  holding mixed instrument and computational data for that molecule (how the example Box and Dropbox
  folders are arranged).

The [roadmap](ROADMAP.md)'s sample-centric phase deep-parses headers to recover the **sample** and
**instrument** for every dataset regardless of folder layout — so you can browse a molecule's complete
data picture across many sources.

## Packaging datasets as `.zip` (recommended)

When uploading example data, **zipping each dataset is the preferred approach** — it compresses to save
storage and keeps every format of a measurement together in one tidy file. PsiDataViz treats a `.zip` as a
single dataset and reads it on demand.

**Best practice — one dataset per zip, multiple formats inside:**

- Put **all the formats of the *same* measurement** in one zip — raw vendor file + ASCII export +
  spreadsheet, e.g. `2025_10_30_Aspirin_MDSC.zip` containing `…MDSC.csv`, `…MDSC.tri`, `…MDSC.xls`.
- **Name the zip like the dataset** (`YYYY_MM_DD_Sample_Technique.zip`); the date/sample/technique are
  recovered from the name.
- The app picks the **most-confidently-parseable** format inside automatically — so a zip holding only a
  Bruker **OPUS `.0`**, a `.dpt`, or a `.csv` all just work — and it understands assembled vendor exports
  (a full **Bruker TopSpin** directory, a **Magritek SpinSolve** export).
- **Nested zips** (a zip inside a zip) are unwrapped automatically (up to a few levels).

**Putting several *different* datasets in one zip** also loads (the app currently surfaces the best one);
expanding a multi-dataset zip into separate records is on the [roadmap](ROADMAP.md). For now, prefer
**one dataset per zip** for the cleanest catalog.
