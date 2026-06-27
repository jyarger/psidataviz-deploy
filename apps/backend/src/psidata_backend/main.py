"""PsiData API — async FastAPI backend that turns the psidata library into a JSON service.

Endpoints (all read-only):
  GET  /api/health
  GET  /api/scan?url=             -> repo summary (datasets-by-technique)
  GET  /api/records?url=&technique=
  GET  /api/dataset?url=&name=&technique=&max_points=
  POST /api/compare   {url, technique, key}  -> cross-format comparison
"""

from __future__ import annotations

import os
import tempfile

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from psidata import __version__, compare_record_formats, get_readers
from psidata.convert import convert as run_convert
from starlette.background import BackgroundTask

from . import molecule as molecule_service
from . import services

app = FastAPI(title="PsiData API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("PSIDATA_CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "readers": [{"technique": r.technique, "name": r.name, "extensions": list(r.extensions)}
                    for r in get_readers()],
    }


@app.get("/api/scan")
def scan(url: str = Query(..., description="GitHub repo URL or owner/repo"),
         filter: str | None = Query(None, description="only include files whose path contains this")) -> dict:
    try:
        return services.scan_summary(services.scan_repo(url, keyword=filter))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not scan {url!r}: {exc}") from exc


@app.get("/api/records")
def records(url: str, technique: str, filter: str | None = None) -> list[dict]:
    catalog = services.scan_repo(url, keyword=filter)
    return [services.record_row(r) for r in catalog.record_groups().get(technique, []) if r.supported]


@app.get("/api/catalog")
def catalog(url: str, filter: str | None = None) -> dict:
    """One source's scan summary plus every supported data record (all techniques) — for the
    multi-source DATA workspace, which merges several catalogs client-side."""
    try:
        cat = services.scan_repo(url, keyword=filter)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not scan {url!r}: {exc}") from exc
    summary = services.scan_summary(cat)
    summary["records"] = [
        services.record_row(r)
        for recs in cat.record_groups().values()
        for r in recs
        if r.supported
    ]
    return summary


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)) -> dict:
    """Receive a dropped local folder/zip, keep it in memory, and return its catalog (same shape as
    /api/catalog) plus an `upload://…` url the DATA workspace uses for follow-up record/dataset calls."""
    collected: dict[str, bytes] = {}
    total = 0
    for f in files:
        data = await f.read()
        total += len(data)
        if total > 250 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Upload too large (250 MB limit).")
        collected[(f.filename or "file").lstrip("/")] = data
    if len(collected) == 1:  # a single dropped .zip is treated as a folder archive — expand it
        (path, blob), = collected.items()
        if path.lower().endswith(".zip"):
            import io
            import zipfile
            try:
                zf = zipfile.ZipFile(io.BytesIO(blob))
                expanded = {m: zf.read(m) for m in zf.namelist()
                            if not m.endswith("/") and "__MACOSX" not in m}
                if expanded:
                    collected = expanded
            except zipfile.BadZipFile:
                pass
    if not collected:
        raise HTTPException(status_code=400, detail="No files received.")
    token = services.store_upload(collected, f"Local upload · {len(collected)} files")
    cat = services.scan_repo(token)
    summary = services.scan_summary(cat)
    summary["records"] = [
        services.record_row(r) for recs in cat.record_groups().values() for r in recs if r.supported
    ]
    summary["url"] = token
    return summary


@app.get("/api/dataset")
def dataset(url: str, name: str, technique: str | None = None, max_points: int = 4000,
            sidecar_url: str | None = None, member: str | None = None) -> dict:
    try:
        ds = services.load_dataset(name, url, technique=technique, sidecar_url=sidecar_url,
                                   member=member)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not load {name!r}: {exc}") from exc
    out = services.dataset_json(ds, max_points=max_points)
    bundle = services.zip_bundle(name, url, technique=technique)
    if bundle:  # a zip holding several datasets -> let the UI switch between them
        out["bundle"] = {"members": bundle, "current": member}
    if out.get("audio"):  # a playable .wav -> URL the <audio> element can stream
        from urllib.parse import quote
        audio_url = f"/api/audio?url={quote(url, safe='')}&name={quote(name, safe='')}"
        if member:
            audio_url += f"&member={quote(member, safe='')}"
        out["audio_url"] = audio_url
    return out


@app.get("/api/audio")
def audio(url: str, name: str, member: str | None = None) -> Response:
    """Stream a `.wav` (a zip member, or directly) as 16-bit PCM so the browser can play it."""
    try:
        data = services.audio_wav(url, name, member=member)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not load audio: {exc}") from exc
    return Response(content=data, media_type="audio/wav")


# fmt -> (file extension, media type)
_CONVERT_FORMATS = {
    "csdf": ("csdf", "application/json"),
    "csdm": ("csdf", "application/json"),
    "jcamp": ("jdx", "chemical/x-jcamp-dx"),
    "jdx": ("jdx", "chemical/x-jcamp-dx"),
    "h5": ("h5", "application/x-hdf5"),
    "hdf5": ("h5", "application/x-hdf5"),
    "csv": ("csv", "text/csv"),
    "parquet": ("parquet", "application/octet-stream"),
    "feather": ("feather", "application/octet-stream"),
    "zip": ("zip", "application/zip"),
}


def _convert_response(url: str, name: str, technique: str | None, fmt: str,
                      member: str | None = None, metadata: dict | None = None):
    fmt = fmt.lower()
    if fmt not in _CONVERT_FORMATS:
        raise HTTPException(status_code=400, detail=f"unsupported format {fmt!r} "
                            f"(use {', '.join(sorted(set(_CONVERT_FORMATS)))})")
    try:
        ds = services.load_dataset(name, url, technique=technique, member=member)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not load {name!r}: {exc}") from exc
    if metadata:  # overlay the user's edited sample / chemical-identity / condition fields
        services.apply_metadata(ds, metadata)

    ext, media = _CONVERT_FORMATS[fmt]
    stem = (ds.metadata.sample_name or ds.source.filename or "dataset").rsplit(".", 1)[0]
    tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
    tmp.close()
    try:
        run_convert(ds, tmp.name, fmt=fmt)
    except Exception as exc:  # noqa: BLE001
        os.unlink(tmp.name)
        raise HTTPException(status_code=400, detail=f"Cannot export {name!r} as {fmt}: {exc}") from exc
    return FileResponse(tmp.name, media_type=media, filename=f"{stem}.{ext}",
                        background=BackgroundTask(lambda: os.unlink(tmp.name)))


@app.get("/api/convert")
def convert_endpoint(url: str, name: str, technique: str | None = None, fmt: str = "csdf",
                     member: str | None = None):
    """Convert a dataset to a standard format and return it as a download."""
    return _convert_response(url, name, technique, fmt, member=member)


@app.post("/api/convert")
def convert_enriched(payload: dict = Body(...)):
    """Convert with user-edited metadata embedded (enriched export from the metadata panel)."""
    return _convert_response(
        payload["url"], payload["name"], payload.get("technique"), payload.get("fmt", "jcamp"),
        member=payload.get("member"), metadata=payload.get("metadata"),
    )


@app.get("/api/molecule")
def molecule(smiles: str | None = None, name: str | None = None, q: str | None = None) -> dict:
    """Resolve a SMILES string or compound name to a 3D structure (mol block) for the viewer.

    ``q`` is free text that is auto-detected (SMILES first, else a name lookup)."""
    if not smiles and not name and not q:
        raise HTTPException(status_code=400, detail="provide a smiles, name, or q parameter")
    try:
        return molecule_service.molecule_payload(smiles=smiles, name=name, q=q)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"structure lookup failed: {exc}") from exc


@app.post("/api/compare")
def compare(payload: dict = Body(...)) -> dict:
    url, technique, key = payload.get("url"), payload.get("technique"), payload.get("key")
    if not (url and technique and key):
        raise HTTPException(status_code=422, detail="url, technique and key are required")
    catalog = services.scan_repo(url)
    record = next((r for r in catalog.record_groups().get(technique, []) if r.key == key), None)
    if record is None:
        raise HTTPException(status_code=404, detail=f"record {key!r} not found")
    return compare_record_formats(record, services.load_dataset)


# Serve the built React frontend (single-service deploy) when its dist is present. Mounted last so
# the /api routes above take precedence; html=True serves index.html for the SPA.
import pathlib  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_static = os.environ.get("PSIDATA_STATIC_DIR") or str(pathlib.Path(__file__).parent / "static")
if os.path.isdir(_static):
    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")


def main() -> None:
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
