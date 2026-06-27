# ΨDataViz — frontend (React + TS + Vite)

The modern dashboard for **PsiDataViz**, talking to the FastAPI backend (`apps/backend`). Plots with
Plotly.js (WebGL). The backend min/max-downsamples large spectra, so payloads stay small.

## Develop

```bash
# 1) start the backend (from the repo root)
uv run --package psidata-backend psidata-api      # http://localhost:8000

# 2) start the frontend
cd apps/frontend && npm install && npm run dev     # http://localhost:5173
```

The dev server proxies `/api` → `http://localhost:8000`, so there are no CORS hops. Point at
`https://github.com/yargerlab/Data` and explore.

## Build

```bash
npm run build      # -> dist/ (static; serve behind any web server, hits the backend via CORS)
```

## Status (vertical slice)

- **QUICK** tab is fully working: scan a repo → technique chips → dataset table (with formats) →
  interactive plot + metadata.
- **DATA / ANALYSIS / VISUALIZATION / ADVANCED** are placeholders for the next phases.

Dark, Ψ-branded; nav `QUICK · DATA · ANALYSIS · VISUALIZATION · ADVANCED`, footer
`Tools · Resources · Contacts`. Replaces the interim Dash app once at parity.
