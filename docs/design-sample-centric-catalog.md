# Design / scoping — Sample-centric catalog

**Status:** decisions agreed (§10); **Lite track complete (phases 1–3 shipped)** — the editable metadata
panel + tags, chemical-identity resolution (name/SMILES → formula/SMILES/CAS + 2D structure), and enriched
export (edited metadata embedded in JCAMP-DX/CSDM, with format recommendations by data type). **Pro track
next.** **Owner:** @jyarger + Claude.
Headlines: **RDKit** for chemical identity · two editions **PsiDataViz Lite** (stateless) & **Pro**
(multi-user + DB + admin) · **top-level by-instrument ⇄ by-sample** plus organizing **unorganized** data ·
**tags** for conditions/instrument/chemical · enriched **CSDM/JCAMP-DX** re-save. The **Lite track**
(phases 1–3, §9) is **done**; the **Pro track** (phases 4–6: PostgreSQL catalog, auth + admin, write-back)
is next.

---

## 1. The problem & the goal

Today PsiDataViz organizes data **by instrument/technique folder** (or infers a technique from a
filename). The recurring pain — called out in review — is that **stored datasets rarely carry enough
about *what* was measured**: the exact instrument, the sample/chemical, conditions, date, operator. This
is worst for bare `.csv`/`.txt`.

**Goal (the north star):** let a researcher browse their data **by sample/compound** — every measurement
of, say, *aspirin* (NMR + DSC + FTIR + computed) gathered in one place, across every connected source —
and make each dataset **self-describing** by capturing the missing metadata (interactively if needed) and
writing it back into an open, standard format.

Two concrete uses:
1. **Browse by compound** across sources (needs a catalog/DB + sample/instrument extraction).
2. **Organize & re-save**: point at / drop a pile of data → PsiDataViz parses it, lets the user fill in
   sample/instrument details, and **re-exports each dataset** in a consistent, information-rich format
   (CSDM / JCAMP-DX / tidy CSV) with identifiers embedded.

---

## 2. Sample identity (chemical) — **SMILES-first**

A "sample" is keyed by a **canonical chemical identity**. Priority, per review:

| Identifier | Role | Notes |
| --- | --- | --- |
| **SMILES** | **primary** | canonicalized; the default we read & write |
| **InChI / InChIKey** | strong key | the InChIKey is the dedup/lookup key (hashable, exact) |
| **CAS RN** | cross-reference | `##CAS REGISTRY NO=` in JCAMP |
| **IUPAC name** | human label | recognized on input; not a reliable key |
| **Molecular formula** | coarse group | `##MOLECULAR FORMULA=` in JCAMP |

- **Canonicalization & conversion** (name⇄SMILES⇄InChI⇄formula) needs a cheminformatics toolkit.
  Candidate: **RDKit** (BSD, the standard) — optional dependency, used server-side. Open question:
  RDKit is a heavyweight wheel; acceptable as a `[chem]` extra in the Docker image?
- **Dedup key:** the **InChIKey** (derived from SMILES via RDKit) groups measurements of the same
  molecule even when users type different SMILES/names.
- Where a structure already exists (computational `.xyz`/`.mol`, or a `.cif`), we can derive SMILES from
  the geometry (RDKit) and link it to the sample.

---

## 3. Where metadata comes from (3 tiers)

1. **Parsed from the file** — readers already extract sample_name/instrument/date where the format has it
   (DSC Trios, JCAMP, OPUS, TGA, …). Best case.
2. **Inferred from the filename/folder** — current `infer_technique` + filename date/description parsing.
3. **Interactive user input** — a metadata panel on the loaded dataset where the user fills/cures:
   **sample** (SMILES / name / CAS / InChI), **instrument** (make/model), conditions (solvent, temp,
   atmosphere), operator, date, location, notes. Pre-filled from tiers 1–2; user confirms/edits.

This interactive layer is valuable **even before a database** — it powers the "re-save" use case.

---

## 4. Re-save in an information-rich standard format

Encourage (and make one-click) conversion to a **self-contained** format with all the curated metadata
embedded. Per review, lead with **CSDM** and **JCAMP-DX**, plus a **tidy CSV** fallback.

**JCAMP-DX header block** we would write (IUPAC CPEP labels, http://www.jcamp-dx.org/):
```
##TITLE=        Acetylsalicylic acid
##DATA TYPE=    INFRARED SPECTRUM
##SMILES=       CC(=O)OC1=CC=CC=C1C(=O)O
##CAS REGISTRY NO= 50-78-2
##MOLECULAR FORMULA= C9H8O4
##NAMES=        aspirin
... (existing ##XUNITS / ##YUNITS / data) ...
```
- **CSDM** (`.csdf`) already supported for export; extend its JSON with a structured
  `sample`/`instrument` block (CSDM has a metadata model for this).
- **Tidy CSV**: the curated fields as a header comment block + the long-form data.
- This directly attacks the "sparse csv/txt" problem: re-saved files become future-proof and FAIR-friendly.

> Docs will explain *why* CSDM/JCAMP-DX (standard labels, embedded identifiers) and link the standards.

---

## 5. The catalog & database

- **Before the DB (stateless):** keep the current scan→records flow; add the interactive-metadata +
  re-save layer (no persistence — the user downloads the enriched file). Ships value immediately.
- **The DB phase:** introduce **PostgreSQL** (standard container, per deployment pref) to persist the
  catalog so users can **browse by sample across sessions/sources**, with tags/labels and search.

**Sketch schema** (PostgreSQL):
```
users(id, email UNIQUE, name, provider, role, created)            -- Pro: oauth/email + admin role
samples(id, inchikey UNIQUE, smiles, iupac_name, cas_rn, formula, names[], created)
instruments(id, make, model, technique, …)
datasets(id, owner_id, sample_id?, instrument_id?, technique, source_url, member, file_name,
         date, operator, conditions JSONB, params JSONB, created)
sources(id, owner_id, url, kind, label, last_scanned)
tags(id, category, name) · dataset_tags(dataset_id, tag_id)       -- category: condition|instrument|chemical
```
- `datasets.conditions/params` as **JSONB** keeps per-technique flexibility without schema churn.
- Sample resolution: on save, RDKit → InChIKey → upsert into `samples`; link the dataset.
- **Auth ties in here** — the `Ψ|Login⟩` placeholder becomes real so uploads/catalog rows are per-user
  (Pro only; the schema leaves room for `owner_id`).

### 5a. Tags & labels

A typed tag taxonomy makes datasets searchable/filterable and seeds the metadata panel's suggestions:

- **Conditions** — solvent, temperature, pressure, atmosphere, date, time, … (the common fields).
- **Instrument** — make/model/technique labels (e.g. *Bruker 500 MHz*, *TA Q2000 DSC*).
- **Chemical** — sample/structure labels (e.g. *aspirin*, *polymorph form II*, *deuterated*).

Stored as `tags(id, category, name)` + `dataset_tags`. Tags start as **free entry with autocomplete**
from existing values; common ones get promoted to typed fields. Available in Lite (session-local, exported
into the enriched file's header) and persisted/searchable in Pro.

---

## 6. Organize & browse — by instrument, by sample, or from chaos

Both layouts are first-class (a top-level **by instrument ⇄ by sample** toggle), and the parser also helps
turn an unorganized pile into either.

- **By instrument / technique** — the current view (folders/inferred technique).
- **By sample / compound** — a searchable list/grid of samples (name + structure thumbnail) → expand to
  every dataset of that molecule across sources, grouped by technique, openable in the existing viewers.
- **Unorganized → organized.** When a user drops a flat pile (or points at a messy source), PsiDataViz
  parses each file, infers **technique** (filename/headers) and **sample** (identifiers/headers, or the
  user fills it in), and proposes an organized view — grouped **by instrument** *or* **by sample** — that
  the user curates. This is the same metadata/identity machinery (§§2–4) applied to triage.

In **Lite** this organizes the current session (and can drive enriched re-save). In **Pro** the organization
is persisted to the catalog and searchable across sessions/sources.

---

## 7. FAIR repositories as sources (later)

- Add a **Chemotion** / FAIR-repo connector (review idea): point a DATA source at a repository like
  chemotion.net and index its chemical datasets. These repos expose APIs and already carry rich
  metadata + identifiers, so they slot into the same `samples`/`datasets` model.
- fairsharing.org as a directory/reference in the docs.

---

## 8. Two editions — PsiDataViz **Lite** and **Pro**

A single codebase, two deployment profiles chosen at install:

| | **Lite** | **Pro** |
| --- | --- | --- |
| Use | quick, private, stateless | a server everyone logs into |
| Auth / users | none | multi-user (Google, GitHub, email) + admin |
| Storage | in-memory per session | **PostgreSQL** catalog (persisted) |
| Browse by sample/instrument | session-local | persisted + searchable across sources |
| Re-save | download enriched file | download **and** write-back / save to the catalog |
| Footprint | one container | app + `postgres:16` (+ auth) via compose |

- **Shared core:** the `psidata` library, the React frontend, and the FastAPI backend are identical. Pro is
  Lite **plus** an auth layer + a DB layer, gated by config (`PSIDATA_MODE=lite|pro`) so Lite ships nothing
  it doesn't use. The frontend hides login / persistence affordances in Lite.
- **Install choice:** `docker run psidataviz` (Lite, today's single image) **or** `docker compose --profile
  pro up` (Pro: app + postgres volume; `DATABASE_URL` + OAuth secrets via env).
- **Portable** to a self-hosted Linux mini-PC, AWS, or Hostinger — compose is the common denominator, no
  cloud-specific services. **Cloudflare** for DNS + reverse proxy / TLS (Tunnel in front of the container);
  documented for the **PsiDataViz** domain. DB migrations via **Alembic** for reproducible schema across hosts.

### 8a. Pro auth & administration

- **Multi-user from the start.** Sign in with **Google** or **GitHub** OAuth, or **email + password**
  (verification + password reset). Standard session/JWT authz; bcrypt-hashed passwords. Candidate stack:
  **Authlib** (OAuth) + **fastapi-users** (or a thin equivalent) over the same Postgres.
- **Per-user data** — uploads and catalog rows carry `owner_id`; sharing/visibility flags later.
- **Admin area** — a secure, admin-only page to manage users (roles, disable/delete), review uploads, and
  see app health/usage. Implemented as a protected route + a small React admin view (or SQLAdmin).

---

## 9. Phased rollout

**Lite track (no DB — ships value now):**
1. **Interactive metadata panel** — editable sample/instrument/conditions fields + **tags** on a loaded
   dataset, pre-filled from parse/inference.
2. **Chemical identity** — RDKit `[chem]` extra; SMILES/InChIKey/CAS/formula resolution + a structure
   preview.
3. **Organize + enriched re-save** — the by-instrument ⇄ by-sample / unorganized triage (§6), and write the
   curated metadata + tags into **CSDM / JCAMP-DX** (`##SMILES=` …) / tidy CSV for **download**.

**Pro track (server edition):**
4. **PostgreSQL catalog + compose** — persist samples/datasets/tags; persisted **browse by sample &
   instrument**; search.
5. **Auth + admin** (`Ψ|Login⟩`) — Google/GitHub/email, password reset, per-user data, admin area; the
   `lite|pro` config split.
6. **Write-back** (save to catalog / export targets) + **FAIR-repo connector** (Chemotion) + the
   Cloudflare/compose deployment playbook.

Phases 1–3 land in **Lite** and are independently shippable; 4–6 build **Pro** on top.

---

## 10. Decisions (from review)

1. **RDKit — yes.** Add it as a server-side `[chem]` extra for SMILES⇄InChI⇄name⇄formula + InChIKey dedup.
2. **Re-save — download-only at first (stateless).** Write-back (and the DB/login it implies) comes with the
   **Pro** edition (see §11). Lite never persists.
3. **Browse-by-sample — top level.** Both *by-instrument* and *by-sample* are first-class, and the parser
   helps organize **unorganized** drops into either (see §6).
4. **Auth (Pro) — multi-user from the start**, with Google + GitHub OAuth and email sign-up (password reset,
   modern session/JWT authz), plus a secure **admin** area for app/user administration (see §11).
5. **Tags/labels — yes.** A tag taxonomy across **conditions** (solvent, temperature, pressure, date/time…),
   **instrument** tags, and **chemical** tags (see §5a).
