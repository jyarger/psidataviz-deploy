# Design decisions

A short log of the choices that shape PsiDataViz, and why — so contributors understand the *intent*, not
just the code.

## Keyless access to public data

**Decision:** read public data with no account, no API key, no OAuth.
**Why:** the typical researcher or student shares data by right-click → "Anyone with the link." They have
never created a Google Cloud key and shouldn't have to. Google Drive is read via the keyless
`embeddedfolderview` listing rather than the Drive API for exactly this reason.

## `psidata` is a standalone library, separate from the app

**Decision:** all parsing, the data model, sources, and conversion live in a pip-installable Python
library with no web dependencies; the app is a thin layer on top.
**Why:** the science is reusable in scripts, marimo, and notebooks, and is testable without the UI. The
app can be replaced or supplemented without touching the core.

## Confidence-scored reader registry with honest `sniff()`

**Decision:** each reader returns a 0–1 confidence from `sniff()`; the registry picks the best match.
Readers must **not** over-claim — only score high for data they can actually decode.
**Why:** formats overlap (many are CSV/JCAMP under the hood). A confidence score resolves ambiguity, and
honesty keeps the catalog's "supported" flag truthful so scans don't promise files that then fail to open.
*(Closing remaining gaps where a scan over-claims is a tracked roadmap item.)*

## Group files into datasets with multiple format variants

**Decision:** files sharing a base name across extensions collapse into one `DataRecord` with several
`FormatVariant`s, classified by role (data / binary / spreadsheet / sidecar / image).
**Why:** one measurement is often saved several ways (`.csv` + vendor binary + spreadsheet). Treating them
as one dataset — and being able to diff the formats — matches how labs actually store data.

## QUICK is simple; DATA / ANALYSIS / VISUALIZATION are advanced

**Decision:** the QUICK tab stays single-source and fast (point, scan, plot). Multi-source combination and
rich per-technique processing live in the other tabs.
**Why:** the 90% case is "I just want to see my data." Power features shouldn't slow that down; they get a
dedicated workspace.

## Organize by sample, not only by instrument

**Decision:** the north-star catalog is browsable by **chemical/compound/sample**, gathering every
measurement of a molecule across sources and instruments.
**Why:** scientists think in terms of *the sample*. Instrument-folder organization is common but partial;
unifying by sample is the project's distinctive goal.

## Stateless for now; database arrives with the sample catalog

**Decision:** keep the app in-memory (re-scan = re-fetch) until the sample-centric phase; introduce the
database then.
**Why:** avoid premature infrastructure. A DB earns its keep once we're persisting parsed metadata, tags,
and a searchable sample index.

## NMR FID → magnitude spectrum

**Decision:** Nanalysis NMReady NTUPLES/FID files are Fourier-transformed to a **magnitude** spectrum
(apodized, zero-filled) on a ppm axis, rather than shown as a raw FID.
**Why:** users expect a spectrum, not a time-domain decay. Magnitude mode is phase-robust — peaks land at
the right chemical shift without guessing phase correction. It's documented as a quick-look, not a fully
phased/referenced spectrum.

## Lightweight CSDM, no heavy dependencies

**Decision:** write the Core Scientific Dataset Model directly as its JSON form instead of depending on
`csdmpy` (which pulls astropy/matplotlib/scipy).
**Why:** keep the library lean. CSDM is a JSON format by design, so the export needs no extra runtime deps.

## Single-image deployment

**Decision:** one container builds the React app and serves it together with the FastAPI API on one port.
**Why:** trivial to run and to host on a small VPS; the app is stateless, so it scales horizontally.

## Apache-2.0 license

**Decision:** Apache License 2.0.
**Why:** permissive (use/fork/modify/commercialize freely) *and* includes an explicit patent grant and
contributor terms — a good fit for an open scientific tool.
