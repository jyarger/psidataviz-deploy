# Architecture

PsiDataViz is three layers, cleanly separated so the science can be used without the app:

```
                    ┌─────────────────────────────────────────────┐
   public data ───▶ │  psidata  (Python library)                  │
  (GitHub/Drive)    │  sources → catalog → readers → model → convert │
                    └───────────────┬─────────────────────────────┘
                                    │ used by
                    ┌───────────────▼─────────────┐      ┌──────────────────┐
                    │  backend  (FastAPI)         │◀────▶│  frontend (React) │
                    │  JSON API + serves the SPA  │      │  QUICK · DATA · …  │
                    └─────────────────────────────┘      └──────────────────┘
```

## 1. `psidata` — the library (`packages/psidata/src/psidata/`)

The framework-agnostic core. Pip-installable; works in scripts, marimo, and Jupyter with no web stack.

- **`model.py`** — the universal container. A `Dataset` has a `technique`, `SourceInfo`, `Metadata`, and a
  list of `Signal`s; each `Signal` has an x/y `Axis` (label, unit, quantity) and a pandas `frame`.
  `Dataset.to_tidy_df()` flattens all signals to one long-form table (used by the CSV/Parquet/Feather
  exporters).
- **`registry.py`** — `@register_reader` registers a reader; `detect()` runs every reader's `sniff()` and
  picks the highest score above `DETECT_THRESHOLD` (0.4); `read()` detects then parses. Adding a reader
  never requires touching the registry or the app.
- **`readers/`** — one module per format. `base.py` defines `BaseReader` (the `sniff`/`read` contract) and
  `Candidate` (lazy, decoded access to file bytes). Shared parsing lives in helpers like `_jcamp.py`
  (LDR + NTUPLES parsing) and `_asdf.py` (the `(X++(Y..Y))` compressed-ordinate decoder).
- **`sources/`** — *where files come from*, independent of *how they're parsed*:
  - `base.py` — the `DataSource` contract and `FileRef` (a discovered file: path, size, download URL).
  - `github.py`, `gdrive.py` — keyless connectors; `make_source(url)` picks the right one.
  - `catalog.py` — `scan()` lists a source and `build_entry()` turns each `FileRef` into a
    `CatalogEntry` (technique from the folder via `canonical_technique()`, plus a `supported` flag from a
    reader match). **No file contents are downloaded during a scan.**
  - `records.py` — `build_records()` groups entries that share a base name into one `DataRecord` with
    several `FormatVariant`s, and `classify_format()` tags each variant (data / binary original /
    spreadsheet / sidecar / image).
- **`convert/`** — `to_csdm` (lightweight CSDM JSON), `to_hdf5`, `to_zarr`, `to_csv`, `to_parquet`,
  `to_feather`, `to_csv_zip`, dispatched by `convert(dataset, path, fmt)`.

## 2. Backend — FastAPI (`apps/backend/`)

A thin async JSON API over the library, which also serves the built React app as static files (so one
container is the whole product).

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Status + the list of registered readers. |
| `GET /api/scan?url=` | Scan a source → per-technique summary counts. |
| `GET /api/records?url=&technique=` | Supported data records for one technique. |
| `GET /api/catalog?url=` | Summary **plus** every supported record (all techniques) — for the DATA workspace. |
| `GET /api/dataset?url=&name=&technique=` | Fetch + parse one dataset; min/max-downsampled to ~4000 points. |
| `GET /api/convert?url=&name=&fmt=` | Convert a dataset and stream the download (csdf/h5/csv/parquet/feather/zip). |
| `POST /api/compare` | Diff a record's format variants. |

`services.py` holds the glue: a process-lifetime cache of source listings (`_listing_cache`), lazy
`load_dataset()`, and JSON serialization with min/max decimation that preserves spectral peaks.

## 3. Frontend — React + TypeScript (`apps/frontend/`)

Vite + TypeScript + Plotly.js (WebGL `scattergl`). `api.ts` is the typed client.

- **QUICK** (`Quick` in `App.tsx`) — one source: scan → technique chips → records table → multi-select
  overlay → normalize/compare → convert. Includes the visual *connect-a-source* helper.
- **DATA** (`DataWorkspace`) — add several sources, then a merged, filterable table and a cross-source
  overlay plot.
- Both views are kept mounted (hidden) when inactive, so their state survives tab switches.

## Data flow

1. **Scan** (cheap, metadata-only) — `list_files()` → `build_entry()` → `build_records()`; the UI shows
   technique counts and a records table. No downloads yet.
2. **Open a dataset** (lazy) — the frontend requests `/api/dataset` with the record's raw download URL;
   the backend fetches the bytes, `read()` parses them into a `Dataset`, and the points are downsampled
   for transport and plotted.
3. **Convert / compare** — operate on the same lazily-loaded datasets.

## Deployment

A multi-stage `Dockerfile` builds the frontend, then runs the backend (uvicorn) serving both the API and
the built SPA on one port. `docker-compose.yml` adds Caddy for automatic TLS. See [deploy.md](deploy.md).
