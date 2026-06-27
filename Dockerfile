# PsiDataViz v2 — single image: build the React frontend, serve it + the API from FastAPI/uvicorn.
# (The interim Dash app's Dockerfile is in git history; this is the primary deployment.)

# ---- stage 1: build the React frontend ----
FROM node:22-slim AS frontend
WORKDIR /fe
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/ ./
RUN npm run build

# ---- stage 2: Python backend serving /api + the built static frontend ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    PSIDATA_STATIC_DIR=/app/static

WORKDIR /app

# Library first (with the [convert] extra so the binary/format readers work in the deployed image:
# FabIO for .edf/.img/.mccd 2D detector images, h5py for .h5, cclib for .log/.out, brukeropusreader
# for OPUS .0, pyarrow for Parquet/Feather), then the backend.
COPY packages/psidata ./packages/psidata
RUN pip install "./packages/psidata[convert]"
COPY apps/backend ./apps/backend
RUN pip install ./apps/backend

# Drop in the built SPA; FastAPI mounts it at / (see psidata_backend.main).
COPY --from=frontend /fe/dist ./static

EXPOSE 8000
CMD ["uvicorn", "psidata_backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
