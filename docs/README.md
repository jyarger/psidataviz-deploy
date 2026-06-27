# PsiDataViz Documentation

Welcome to the PsiDataViz docs. This is the reference for how the project works, where it's going, and
how to extend it.

> **The two pieces:** **`psidata`** is the standalone Python library (the data model, reader registry,
> source connectors, conversion). **PsiDataViz** is the web app (FastAPI + React) built on top of it.

## Contents

| Doc | What's in it |
| --- | --- |
| [Roadmap](ROADMAP.md) | The vision, what's built, and the prioritized plan ahead. |
| [Architecture](architecture.md) | How the library, backend, and frontend fit together, and how data flows. |
| [Data sources](data-sources.md) | Connecting public data (GitHub, Google Drive, Box/Dropbox), and how scanning turns files into datasets. |
| [Adding a reader](adding-a-reader.md) | The high-value contribution path: teach PsiData a new format. |
| [Design decisions](design-decisions.md) | Why the project is built the way it is (an ADR-style log). |
| [Deployment](deploy.md) | Running PsiDataViz on a public VPS behind TLS. |

## Status snapshot

- **Readers today:** DSC (TA Trios), NMR (JCAMP-DX incl. ASDF & Nanalysis NMReady FID→spectrum, `.tsv`,
  2D TopSpin `totxt`), FTIR (Bruker `.dpt`, JCAMP, PerkinElmer `.asc`), Raman, XRD (1D ASCII), UV-Vis.
- **Sources today:** public GitHub repos and Google Drive folders — **keyless** (no API keys). Box and
  Dropbox are planned.
- **App:** **QUICK** (one source: scan → overlay → compare → convert) and **DATA** (a multi-source
  workspace). **ANALYSIS / VISUALIZATION / ADVANCED** are where richer per-technique tools will live.

See the [Roadmap](ROADMAP.md) for what's next — parsing breadth is the current top priority.

## Contributing

The most valuable contribution is a **new reader** for a format we don't yet cover. See
[Adding a reader](adding-a-reader.md) and [../CONTRIBUTING.md](../CONTRIBUTING.md), and open a
[data-format request](../.github/ISSUE_TEMPLATE) for anything that fails to parse.
