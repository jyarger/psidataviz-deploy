# PsiDataViz — Roadmap

## Vision

Scientific data is scattered across instruments, formats, and cloud drives. PsiDataViz aims to:

1. **Read everything.** Parse and visualize *all* major kinds of experimental and computational
   scientific data — ~24 technique families read today, and growing.
2. **Organize by sample, not just by instrument.** Let a researcher browse their data by the
   **chemical/compound/sample**, gathering every measurement of a molecule in one place — sourced from
   many public locations.
3. **Stay frictionless and open.** Public data scans with **no account and no API key**; the whole thing
   is open source (Apache-2.0) and self-hostable.

## Built so far

- **`psidata` library** — universal `Dataset`/`Signal`/`Axis`/`Metadata` model; a confidence-scored
  reader **registry**; file → `DataRecord` grouping (one dataset, many format variants) with format
  comparison; conversion to CSDM/HDF5/Zarr/CSV/Parquet/Feather.
- **Readers** — DSC, NMR (JCAMP-DX + ASDF, Nanalysis NMReady NTUPLES/FID→spectrum, `.tsv`, 2D `totxt`),
  FTIR (`.dpt`, JCAMP, PerkinElmer `.asc`, **Bruker OPUS `.0`** via brukeropusreader), Raman, XRD (1D —
  `.xy`, PANalytical `.csv`/`.xrdml`/`.udf`, `.dat`/`.asc`; 2D detector images via FabIO), **microscopy**
  (SEM/TEM/optical `.tif`/`.jpg`/`.png` micrographs via Pillow + Gatan TEM `.dm3`/`.dm4` via ncempy),
  **electrochemistry** (Gamry `.DTA` CV +
  **Chemotion** JCAMP-DX `.jdx` exports → Potential × Current), **mass spec & SIMS** (ChemSpectra JCAMP-DX
  `MASS SPECTRUM`, standard MS and secondary-ion MS grouped separately), **dielectric** (broadband ε′/ε″ vs
  frequency, log axis), **HPLC** (chromatogram CSV + Agilent ChemStation DAD `.D` runs inside `.tar.bz2`),
  **circular dichroism** (`.dcs`), **generic spreadsheets** (`.xlsx`/`.xls` via openpyxl/xlrd — auto-finds
  the data table; used for Mechanical test data), UV-Vis
  (`.txt` / Thorlabs `.csv`), **TGA** (TA Instruments `.txt`), **Brillouin** (multichannel-scaler `.asc`),
  **Acoustic** (interferometry FFT `Spectrum.csv` inside the `.zip`), **Computational** (`.log`/`.out` via
  **cclib** → IR/Raman, plus GaussView `_ir.txt`/`_raman.txt`, and `.gjf`/`.inp` input geometries).
- **Sources** — keyless **GitHub**, **Google Drive**, **Codeberg**, and **Box** connectors behind one
  `make_source()` factory; technique-folder normalization (e.g. `IR` → `FTIR`) and, for sample-organized
  sources, technique **inferred from the filename**.
- **3D structure viewer** — **3Dmol.js** renders structure files and a computational job's optimized
  geometry beside the data; **vibrational normal modes animate** (pick a mode, or click the spectrum peak).
- **Molecule viewer everywhere** — type a **SMILES** or a **compound name** (RDKit embeds → 3D; PubChem
  resolves names) to see any structure; it **auto-shows the compound** when a dataset's name implies one
  (e.g. a CBD Raman spectrum displays cannabidiol). Shown for any dataset without a computed structure.
- **Interactive visualization** — **mass spectra** render as stick/peak plots; an **HPLC-DAD wavelength
  slider** scrubs the time×wavelength matrix to any wavelength; log/linear axis hints per technique.
- **Editable metadata panel** (Ψ|Data⟩) — under each loaded dataset, sample / instrument / conditions
  fields pre-filled from the parse, plus tags (condition / instrument / chemical). Stateless for now;
  the first step of the sample-centric catalog (Lite track).
- **ΨDataSound** — acoustic `.wav` recordings play in the browser (16-bit PCM re-encode) with a
  waveform / FFT-spectrum toggle.
- **PsiDataViz app** — FastAPI backend + React/TS frontend, single-image deploy. **QUICK** tab
  (scan → filter → overlay → compare → convert) and **DATA** tab (multi-source workspace + metadata).
- **Open source** — public repo, Apache-2.0, CI (lint + tests + build), issue/PR templates.

## Next up  ·  *immediate sequence*

Parsing breadth is now broad (~24 technique families) and the **sample-centric catalog** has begun on the
**Lite track** ([design doc](design-sample-centric-catalog.md)):

1. **Catalog Lite — phase 2: chemical identity** — wire the metadata panel's SMILES/CAS/name fields to
   RDKit + PubChem (name → SMILES → formula, structure inline); the `/api/molecule` endpoint already does
   most of it.
2. **Catalog Lite — phase 3: enriched export** — feed the edited metadata + tags into the convert endpoint
   so CSDM / JCAMP-DX downloads carry `##SMILES=`, `##CAS REGISTRY NO=`, conditions, etc.
3. **Catalog Pro track** — PostgreSQL catalog, multi-user auth (Google/GitHub/email) + admin, browse by
   sample & instrument, write-back (the `lite|pro` editions).
4. **More interactivity** (ongoing) — keep adding sliders/linked views; **remaining readers** are minor
   (Mechanical `.mss` OLE2; the `.xls` already covers it). Then **VPS deploy + Cloudflare domain**.

## Prioritized plan

### 1 — Parsing breadth & robustness  ·  *highest priority*

The core mission. PsiDataViz is only as useful as the formats it can read.

- **Parse-diagnostics framework** ✅ — the scan reports a **coverage %** and the **formats present but
  unread, ranked by count** (a "Parsing coverage" panel in QUICK), with a one-click data-format request.
  Makes coverage gaps visible and prioritizable. *Next:* per-file load-failure reasons, not just unread
  extensions.
- **Honest detection** — `sniff()` should never claim a format it can't actually decode (a scan must not
  flag a file "supported" that then fails to load).
- **Archive bundles** — a `.zip` **or a tarball** (`.tar.bz2`/`.tar.gz`/`.tgz`, plus single `.bz2`/`.gz`)
  is read as one dataset (tarballs are repackaged into a zip so the whole zip pipeline applies): vendor
  multi-file exports (Bruker TopSpin, SpinSolve) are assembled, otherwise the **most-confidently-parseable
  member is chosen via the full reader registry** (so an OPUS-`.0`-only or structure-only archive works,
  or a `.tar.bz2` of Agilent ChemStation `.D` runs), and **nested zips** are unwrapped.
  Zipping each dataset (all its formats together) is the recommended upload pattern — see
  [data-sources](data-sources.md#packaging-datasets-as-zip-recommended). A zip that holds **several
  distinct datasets** is expanded too: the inner datasets are listed and the UI lets you switch between
  them (e.g. a zip of nine OPUS measurements → nine selectable spectra).
- **New techniques** — XRD 1D (ASCII + PANalytical `.xrdml`/`.udf`), **2D XRD/SAXS detector images**
  (`.edf`, `.img` ADSC, `.mccd` MarCCD, `.tif`/`.raw.tif` via **FabIO**, NeXus `.h5` via h5py — shown as
  heatmaps), UV-Vis ASCII, and zipped Bruker/SpinSolve NMR readers are in. Calibrated detector frames are
  also **azimuthally integrated to a 1D pattern I(2θ)** from the header geometry (distance/centre/pixel/λ),
  shown alongside the heatmap. **Computed IR/Raman spectra** (GaussView `_ir.txt`/`_raman.txt` exports from
  Gaussian/ORCA/Psi4 frequency jobs, with the DFT method from the filename) read on a wavenumber axis for
  overlay on experiment. **Quantum-chemistry outputs** (`.log`/`.out`) are now parsed directly with
  **cclib** (Gaussian/ORCA/Q-Chem/NWChem/Psi4): vibrational frequencies + IR/Raman intensities are
  Lorentzian-broadened into spectra, and the optimized geometry + normal modes feed the 3D viewer (§3).
  Molecular **structure files** (`.xyz`/`.mol`/`.sdf`/`.pdb`/`.cif`), **TGA** (TA Instruments
  thermogravimetric `.txt` → weight % vs temperature), and **Gaussian/ORCA input geometries**
  (`.gjf`/`.com`/`.inp` → 3D viewer) read too. The coverage panel now lists **per-dataset reasons** (which
  files, and why). Still to do: proper **pyFAI** corrections + arbitrary `.poni` calibration, Z-matrix
  inputs, more proprietary-binary export guidance, and more.

### 2 — Sample-centric catalog  ·  *the north star*

- **More sources** — keyless **Codeberg** (Gitea) and **Box** (scrapes each shared-folder page's
  `Box.postStreamData`) are in. **Dropbox** (public folder only exposes a ~700 MB whole-folder zip; per-file
  listing is CSRF-gated) and **Proton Drive** (E2E-encrypted) remain open in
  [#4](https://github.com/jyarger/PsiDataViz/issues/4).
- **Organize by sample.** Some sources are organized by instrument (GitHub, Drive); others by chemical
  (Codeberg/Box/Dropbox folders named `Aspirin`, `CBD`, …). A first step is in — when the top folder is a
  compound (no instrument reader), the technique is **inferred from the filename**. Next: deep-parse
  headers/notes to determine the **sample** *and* **instrument** for every dataset regardless of folder
  layout, then let users **browse by sample**.
- Introduces the project's first **database** + tags/labels for a searchable catalog.
- **Design/scoping doc:** [design-sample-centric-catalog.md](design-sample-centric-catalog.md) — sample
  identity (SMILES/InChI/CAS), interactive metadata + enriched re-save (CSDM/JCAMP-DX), the PostgreSQL
  catalog, browse-by-compound, FAIR-repo sources, and Docker/Cloudflare deployment. Phased rollout inside.

### 3 — Advanced per-technique analysis & visualization

**QUICK stays simple** — scan, basic overlay/plot, basic 3D view, convert. The rich, **interactive,
linked-view** experiences live in **DATA / ANALYSIS / VISUALIZATION / ADVANCED**, where panels sync:
clicking a spectral feature drives the structure/other panels, and vice-versa (the QUICK
spectrum-peak → vibration animation is the simplest taste of this).

**Viewer strategy:** **3Dmol.js** is the default everywhere (lightweight; great for molecules + computed
normal modes). **Mol\*** is introduced in **ADVANCED/VISUALIZATION** specifically for **MD trajectories**
(the example data includes NAMD/GROMACS runs) and large/crystal structures, behind the existing viewer
abstraction — so we add the heavyweight tool only where it earns its keep, not as a wholesale swap.

Lives in the **ANALYSIS / VISUALIZATION** tabs (QUICK stays simple):

- **NMR** — NMRium-grade interactivity: referencing, peak picking, integration, phasing.
- **DSC** — select heating/cooling scans; glass transition; peak integration (enthalpy).
- **IR / Raman** — overlay experimental spectra with **computed** spectra (from Gaussian/ORCA/Psi4 …,
  now read via cclib).
- **3D structure viewer** (**3Dmol.js**) ✅ — molecular/crystal structure files
  (`.xyz`/`.mol`/`.sdf`/`.pdb`/`.cif`) and a computational job's **optimized geometry** (from cclib) render
  in an interactive viewer beside the data, so a Gaussian/ORCA `.log` shows its IR/Raman spectra *and* its
  molecule. **Vibrational normal modes animate** — pick a mode (frequency + IR strength, from cclib
  `vibdisps`) and the atoms oscillate along it, **or click the peak on the spectrum** to animate its mode.
  *Next:* cube files (MOs/density) and crystal unit cells; Mol\* behind a thin abstraction for large
  biomolecules. Tracked in [#5](https://github.com/jyarger/PsiDataViz/issues/5).
- Multiple datasets per plot, and series/grids of subplots.

### 4 — Documentation & feedback

- Wiki-style docs with a table of contents (this `docs/` set is the start).
- An in-app **feedback form** (routed to the maintainer or stored for review).

### 5 — Large-dataset handling

Big NMR and image-based techniques (XRD/TEM/SEM produce large 2D arrays) need a strategy:
server-side downsampling, tiling/streaming, lazy loading, and Arrow/Parquet transport.

### 6 — Deployment

Reserve the **PsiDataViz** domain and deploy on a cloud VPS so anyone can use it for their own public
data, with clear install directions (see [deploy.md](deploy.md)).

## Principles

- **Keyless first** — public links should work with no credentials.
- **QUICK is simple, DATA/ANALYSIS/VISUALIZATION are advanced.**
- **Source- and format-agnostic core** — new sources and readers slot in without touching the app.
- **Honest about failure** — show what didn't parse and why, and iterate.
