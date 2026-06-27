"""Data-access + serialization glue for the API. Thin wrappers over the psidata library."""

from __future__ import annotations

import io
import os
import uuid
import zipfile
from collections import Counter, OrderedDict
from dataclasses import asdict
from functools import lru_cache

import httpx
import numpy as np
from psidata import Candidate, Dataset, archive_datasets, is_archive, read, read_archive
from psidata.readers.raman_text import parse_spec_sidecar
from psidata.sources import Catalog, FileRef, make_source
from psidata.sources.catalog import _technique_has_reader, build_entry, detect_organization
from psidata.sources.chemotion import ZIP_MEMBER_SEP
from psidata.sources.gdrive import download_drive
from psidata.sources.records import IMAGE

_listing_cache: dict[str, dict] = {}  # url -> {"label", "files"} (process-lifetime cache)

# Locally-uploaded data (drag-and-drop): kept in memory, addressed by an "upload://<id>|<path>" URL so it
# flows through the same scan/records/dataset pipeline. LRU-capped (drag-drop is per-session, not storage).
_UPLOAD_STORE: OrderedDict[str, dict[str, bytes]] = OrderedDict()
_UPLOAD_MAX = 12
UPLOAD_SCHEME = "upload://"


def store_upload(files: dict[str, bytes], label: str) -> str:
    """Stash uploaded files in memory and pre-fill the listing cache so scan_repo() can read them."""
    upload_id = uuid.uuid4().hex[:12]
    _UPLOAD_STORE[upload_id] = files
    _UPLOAD_STORE.move_to_end(upload_id)
    while len(_UPLOAD_STORE) > _UPLOAD_MAX:
        evicted, _ = _UPLOAD_STORE.popitem(last=False)
        _listing_cache.pop(f"{UPLOAD_SCHEME}{evicted}", None)
    refs = [FileRef(path=p, size=len(b), download_url=f"{UPLOAD_SCHEME}{upload_id}|{p}")
            for p, b in files.items()]
    _listing_cache[f"{UPLOAD_SCHEME}{upload_id}"] = {"label": label,
                                                     "files": [asdict(r) for r in refs]}
    return f"{UPLOAD_SCHEME}{upload_id}"


def scan_repo(url: str, *, use_cache: bool = True, keyword: str | None = None) -> Catalog:
    payload = _listing_cache.get(url) if use_cache else None
    if payload is None:
        src = make_source(url)
        try:
            payload = {"label": src.label, "files": [asdict(r) for r in src.list_files()]}
        finally:
            getattr(src, "close", lambda: None)()
        _listing_cache[url] = payload  # cache the *full* listing; the keyword just filters it in memory
    refs = [FileRef(**f) for f in payload["files"]]
    if keyword:
        kw = keyword.strip().lower()
        refs = [r for r in refs if kw in r.path.lower()]
    return Catalog(source_label=payload["label"], entries=[build_entry(r) for r in refs])


@lru_cache(maxsize=6)
def _download_archive(url: str) -> bytes:
    """Download (and process-cache) a whole archive — used to serve many inner members of one
    Chemotion/BagIt zip without re-downloading the multi-megabyte archive each time."""
    resp = httpx.get(url, follow_redirects=True, timeout=180.0)
    resp.raise_for_status()
    return resp.content


def _fetch_bytes(url: str) -> bytes:
    if url.startswith(UPLOAD_SCHEME):  # locally-uploaded data, served from memory
        upload_id, _, path = url[len(UPLOAD_SCHEME):].partition("|")
        store = _UPLOAD_STORE.get(upload_id)
        if store is None or path not in store:
            raise FileNotFoundError("Uploaded data not found (it may have expired — drop the files again).")
        return store[path]
    marker = ".zip" + ZIP_MEMBER_SEP  # "<archive>.zip!<member>" -> extract that member
    if marker in url.lower():
        cut = url.lower().index(marker) + len(".zip")
        zip_url, member = url[:cut], url[cut + len(ZIP_MEMBER_SEP):]
        return zipfile.ZipFile(io.BytesIO(_download_archive(zip_url))).read(member)
    if "drive.google.com/uc" in url:  # follow Drive's large-file virus-scan confirm interstitial
        return download_drive(url)
    headers = {}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "githubusercontent" in url:
        headers["Authorization"] = f"Bearer {token}"
    resp = httpx.get(url, follow_redirects=True, timeout=120.0, headers=headers)
    resp.raise_for_status()
    return resp.content


@lru_cache(maxsize=3)
def _fetch_archive(url: str) -> bytes:
    """Whole-archive bytes, process-cached so switching between datasets inside a multi-dataset zip
    (e.g. a numbered-subfolder Bruker NMR archive) doesn't re-download the archive each time."""
    return _fetch_bytes(url)


def load_dataset(name: str, url: str, *, technique: str | None = None,
                 sidecar_url: str | None = None, member: str | None = None) -> Dataset:
    archive = is_archive(name) or is_archive(url)
    content = _fetch_archive(url) if archive else _fetch_bytes(url)
    if archive:
        ds = read_archive(name, content, technique_hint=technique, member=member)
    else:
        ds = read(Candidate(filename=name, content=content, uri=url, technique_hint=technique))
    if sidecar_url:  # merge a Raman *_spec.txt companion (laser/power/spectrometer) into metadata
        try:
            ds.metadata.extra.update(parse_spec_sidecar(_fetch_bytes(sidecar_url).decode("utf-8", "replace")))
        except Exception:  # noqa: BLE001  a missing/odd sidecar must never break the dataset
            pass
    return ds


_EDITABLE_META = ("sample_name", "instrument", "operator", "date", "time", "solvent",
                  "temperature", "pressure", "formula", "smiles", "cas", "notes")


def apply_metadata(dataset: Dataset, overrides: dict) -> None:
    """Overlay the user's edited metadata (sample / chemical identity / conditions / tags) onto a loaded
    dataset, so an enriched export carries it. Unknown keys land in the (extra-allowing) Metadata model."""
    meta = dataset.metadata
    for key in _EDITABLE_META:
        value = overrides.get(key)
        if value not in (None, ""):
            setattr(meta, key, value)
    if overrides.get("tags"):
        meta.tags = overrides["tags"]


def zip_bundle(name: str, url: str, *, technique: str | None = None) -> list[dict]:
    """The distinct datasets inside an archive (empty for a non-archive or single-dataset one). Cheap:
    the bytes are already cached by ``_fetch_bytes`` from the dataset load."""
    if not (is_archive(name) or is_archive(url)):
        return []
    members = archive_datasets(name, _fetch_archive(url), technique_hint=technique)
    return members if len(members) > 1 else []


# --- JSON serialization -----------------------------------------------------------------------
def scan_summary(catalog: Catalog) -> dict:
    summary = catalog.summary()
    groups = catalog.record_groups()
    techniques = [
        {
            "technique": tech,
            "n_datasets": sum(r.is_data_record for r in recs),
            "n_supported": sum(r.supported for r in recs),
        }
        for tech, recs in groups.items()
        if any(r.is_data_record for r in recs)
    ]
    techniques.sort(key=lambda t: (-t["n_supported"], t["technique"]))
    # COMPOUND dimension: how many supported datasets each inferred sample/compound has
    compounds: Counter[str] = Counter()
    for recs in groups.values():
        for r in recs:
            if r.supported and r.compound:
                compounds[r.compound] += 1
    compound_list = [{"compound": c, "n_supported": n} for c, n in compounds.most_common()]
    return {
        "source": summary["source"],
        "n_files": summary["n_files"],
        "n_records": summary["n_records"],
        "n_data_records": summary["n_data_records"],
        "n_supported_records": summary["n_supported_records"],
        "techniques": techniques,
        "compounds": compound_list,
        "organization": detect_organization(catalog.entries),
        "diagnostics": _diagnostics(groups, summary),
    }


# Recognized formats we can't (or won't) parse directly, with guidance. (note, how-to-convert).
_FORMAT_NOTES: dict[str, tuple[str, str | None]] = {
    ".tri": ("TA Instruments Trios proprietary binary (DSC)",
             "Export to .txt or .xls from Trios — PsiDataViz reads those."),
    ".sp": ("PerkinElmer FTIR proprietary binary", "Export to .dpt or .csv from Spectrum."),
    ".spa": ("Thermo OMNIC proprietary binary (IR)", "Export to JCAMP (.dx) or .csv from OMNIC."),
    ".spc": ("Galactic/Thermo SPC proprietary binary", "Export to ASCII / .csv."),
    ".spf2": ("Spectrometer proprietary binary (UV-Vis)", "Export to .csv or .txt."),
    ".chk": ("Gaussian checkpoint (binary state, not a spectrum)",
             "Use the .log, or the exported _ir.txt / _raman.txt."),
    ".gbw": ("ORCA binary wavefunction (not a spectrum)", "Use the ORCA .out."),
    ".densities": ("Computational density data (not a spectrum)", None),
    ".densitiesinfo": ("Computational density metadata", None),
    ".itp": ("GROMACS topology (molecular dynamics)", None),
    ".gro": ("GROMACS coordinates (molecular dynamics)", None),
    ".bibtex": ("Bibliography / references (not data)", None),
}


def _diagnostics(groups: dict, summary: dict) -> dict:
    """What didn't parse and why — coverage plus the formats present but unread, ranked by count.

    Drives the iterate-on-coverage loop: the highest-count unread extensions are where adding a reader
    helps most. ``unread_formats`` counts the data-variant extensions of datasets with no usable reader,
    annotated with guidance for formats we recognize as proprietary/binary (e.g. ``.tri``).
    """
    unread: Counter[str] = Counter()
    unread_techniques: Counter[str] = Counter()
    unread_items: list[dict] = []
    for tech, recs in groups.items():
        for r in recs:
            if r.is_data_record and not r.supported:
                unread_techniques[tech] += 1
                for v in r.data_variants:
                    unread[v.ext] += 1
                unread_items.append(_unread_item(r, tech))
    n_data = summary["n_data_records"]
    n_ok = summary["n_supported_records"]
    return {
        "coverage": round(100 * n_ok / n_data, 1) if n_data else 0.0,
        "n_supported": n_ok,
        "n_unsupported": n_data - n_ok,
        "unread_formats": [_unread_entry(ext, n) for ext, n in unread.most_common(14)],
        "unread_by_technique": [{"technique": t, "count": n}
                                for t, n in unread_techniques.most_common()],
        "unread_items": unread_items[:60],  # per-dataset breakdown (which files, and why)
    }


def _unread_item(record, technique: str) -> dict:
    """Why one dataset isn't readable: its data extensions plus the most specific reason we can give
    without downloading it (a known proprietary/binary note, else 'no reader yet')."""
    exts = sorted({v.ext for v in record.data_variants})
    noted = next((e for e in exts if e in _FORMAT_NOTES), exts[0] if exts else "")
    note = _FORMAT_NOTES.get(noted)
    name = record.data_variants[0].file.name if record.data_variants else record.key
    if note:  # a known proprietary/binary/non-data format -> the specific guidance
        reason, hint = note[0], note[1]
    elif not _technique_has_reader(technique):  # the whole technique has no reader yet
        reason, hint = f"No reader for {technique} data yet", None
    else:  # technique is read, but not this particular format
        reason, hint = f"No reader for {noted or 'this format'} yet", None
    return {"name": name, "technique": technique, "formats": exts, "reason": reason, "hint": hint}


def _unread_entry(ext: str, count: int) -> dict:
    entry = {"ext": ext, "count": count}
    note = _FORMAT_NOTES.get(ext)
    if note:
        entry["note"] = note[0]
        if note[1]:
            entry["hint"] = note[1]
    return entry


def record_row(record) -> dict:
    data_exts = sorted({v.ext for v in record.data_variants})
    extras = []
    if record.sidecars:
        extras.append("params")
    if any(v.info.role == IMAGE for v in record.variants):
        extras.append("img")
    spec = next((v for v in record.sidecars if v.file.name.lower().endswith("_spec.txt")), None)
    return {
        "key": record.key,
        "uid": record.uid,
        "technique": record.technique,
        "compound": record.compound,
        "date": record.parsed.date.isoformat() if record.parsed.date else None,
        "description": record.parsed.description,
        "formats": data_exts,
        "extras": extras,
        "primary": record.primary.ext,
        "name": record.primary.file.name,
        "url": record.primary.file.download_url,
        "sidecar_url": spec.file.download_url if spec else None,
    }


def dataset_json(dataset: Dataset, max_points: int = 4000) -> dict:
    meta = {k: v for k, v in dataset.metadata.model_dump().items() if v not in (None, [], {})}
    meta.update(meta.pop("extra", {}))  # surface sidecar fields (laser/power/…) at the top level
    return {
        "technique": dataset.technique,
        "filename": dataset.source.filename,
        "reader": dataset.source.reader,
        "metadata": meta,
        "signals": [
            {
                "name": sig.name,
                "segment": sig.segment,
                "x": {"label": sig.x.label, "unit": sig.x.unit, "quantity": sig.x.quantity,
                      "scale": sig.x.scale},
                "y": {"label": sig.y.label, "unit": sig.y.unit, "quantity": sig.y.quantity,
                      "scale": sig.y.scale},
                "points": _downsample(sig.frame[sig.x.label].to_numpy(),
                                      sig.frame[sig.y.label].to_numpy(), max_points),
            }
            for sig in dataset.signals
        ],
        "images": [_image_json(im) for im in dataset.images],
        "structure": (
            {
                "data": dataset.structure.data,
                "format": dataset.structure.fmt,
                "title": dataset.structure.title,
                "n_atoms": dataset.structure.n_atoms,
                "modes": [
                    {"freq": m.freq, "ir": m.ir, "raman": m.raman, "disps": m.disps}
                    for m in dataset.structure.modes
                ],
            }
            if dataset.structure else None
        ),
        "audio": (
            {"sample_rate": dataset.audio.sample_rate, "n_samples": dataset.audio.n_samples,
             "channels": dataset.audio.channels, "duration": round(dataset.audio.duration, 3)}
            if dataset.audio else None
        ),
    }


def audio_wav(url: str, name: str, member: str | None = None) -> bytes:
    """Fetch a ``.wav`` (a zip member, or directly) and re-encode it as plain 16-bit PCM for playback."""
    from psidata.readers.wav_audio import read_wav, to_pcm16_wav

    content = _fetch_bytes(url)
    if member or name.lower().endswith(".zip") or url.lower().endswith(".zip"):
        import io
        import zipfile
        if not member:
            raise ValueError("a zip audio request needs a member")
        content = zipfile.ZipFile(io.BytesIO(content)).read(member)
    sample_rate, _channels, samples = read_wav(content)
    return to_pcm16_wav(samples, sample_rate)


def _image_json(image, max_side: int = 240) -> dict:
    """A scientific map -> downsampled log-scaled heatmap; a micrograph (`photo`) -> a real image; a
    `matrix` (e.g. HPLC-DAD time x wavelength) -> the linear grid + axis coordinates for UI slicing."""
    kind = getattr(image, "kind", "map")
    if kind == "photo":
        return _photo_json(image)
    if kind == "matrix":
        return _matrix_json(image)
    if kind == "nmr2d":
        return _nmr2d_json(image)
    a = image.data
    rows, cols = a.shape
    step = max(1, -(-max(rows, cols) // max_side))  # ceil division -> longest side <= max_side
    if step > 1:  # block max-pool keeps diffraction peaks/rings visible
        r, c = (rows // step) * step, (cols // step) * step
        a = a[:r, :c].reshape(r // step, step, c // step, step).max(axis=(1, 3))
    z = np.log1p(np.clip(np.nan_to_num(a, nan=0.0), 0, None))
    return {
        "name": image.name,
        "x": {"label": image.x.label, "unit": image.x.unit},
        "y": {"label": image.y.label, "unit": image.y.unit},
        "z": {"label": image.z.label, "unit": image.z.unit, "scale": "log1p"},
        "shape": [int(rows), int(cols)],
        "values": np.round(z, 3).tolist(),
    }


def _nmr2d_json(image, max_side: int = 256) -> dict:
    """A 2D NMR spectrum (signed intensity over two ppm axes) for a contour view. Down-sampled by
    abs-max pooling so sparse cross-peaks survive, with the real F2 (x) and F1 (y) ppm coordinates."""
    a = np.nan_to_num(image.data, nan=0.0)
    rows, cols = a.shape
    rstep = max(1, -(-rows // max_side))
    cstep = max(1, -(-cols // max_side))
    xv = image.x_values if image.x_values is not None else np.arange(cols, dtype=float)
    yv = image.y_values if image.y_values is not None else np.arange(rows, dtype=float)
    if rstep > 1 or cstep > 1:
        r, c = (rows // rstep) * rstep, (cols // cstep) * cstep
        blocks = a[:r, :c].reshape(r // rstep, rstep, c // cstep, cstep).transpose(0, 2, 1, 3)
        blocks = blocks.reshape(blocks.shape[0], blocks.shape[1], -1)
        pick = np.abs(blocks).argmax(axis=2)  # keep the signed extreme of each block
        a = np.take_along_axis(blocks, pick[:, :, None], axis=2)[:, :, 0]
        xv, yv = xv[:c:cstep], yv[:r:rstep]
    mag = np.abs(a[np.isfinite(a)])
    # contour start just above the noise floor; the cross-peaks live in the top percentile
    level = float(np.percentile(mag, 99.0)) if mag.size else 1.0
    zmax = float(mag.max()) if mag.size else 1.0
    return {
        "name": image.name,
        "kind": "nmr2d",
        "x": {"label": image.x.label, "unit": image.x.unit, "values": np.round(xv, 4).tolist()},
        "y": {"label": image.y.label, "unit": image.y.unit, "values": np.round(yv, 4).tolist()},
        "z": {"label": image.z.label, "unit": image.z.unit, "level": round(level, 3), "max": round(zmax, 3)},
        "shape": [int(a.shape[0]), int(a.shape[1])],
        "values": np.round(a, 3).tolist(),
    }


def _matrix_json(image, max_cols: int = 600) -> dict:
    """Linear grid + real axis coordinates, for a UI that slices it interactively (a row/column at a
    time). Rows (y) are kept at full resolution (the slider granularity); columns (x) are downsampled."""
    a = np.nan_to_num(image.data, nan=0.0)
    rows, cols = a.shape
    step = max(1, cols // max_cols)
    a = a[:, ::step]
    xv = image.x_values[::step] if image.x_values is not None else np.arange(a.shape[1], dtype=float)
    yv = image.y_values if image.y_values is not None else np.arange(rows, dtype=float)
    return {
        "name": image.name,
        "kind": "matrix",
        "x": {"label": image.x.label, "unit": image.x.unit, "values": np.round(xv, 4).tolist()},
        "y": {"label": image.y.label, "unit": image.y.unit, "values": np.round(yv, 3).tolist()},
        "z": {"label": image.z.label, "unit": image.z.unit},
        "shape": [int(rows), int(a.shape[1])],
        "values": np.round(a, 3).tolist(),
    }


def _photo_json(image, max_side: int = 1100) -> dict:
    """Encode a micrograph (grayscale or RGB) as a downsampled PNG data-URI shown as-is in the UI."""
    import base64
    import io

    from PIL import Image as PILImage

    a = image.data
    if a.dtype != np.uint8:  # normalize 16-bit / float micrographs to 8-bit for display
        a = np.nan_to_num(a, nan=0.0)
        hi = float(a.max()) or 1.0
        a = (np.clip(a, 0, hi) / hi * 255.0).astype(np.uint8) if hi > 255 else a.astype(np.uint8)
    pil = PILImage.fromarray(a)
    pil.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    pil.convert("RGB").save(buf, format="JPEG", quality=85)  # JPEG keeps the data-URI small
    uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return {
        "name": image.name,
        "kind": "photo",
        "data_uri": uri,
        "shape": [int(image.shape[0]), int(image.shape[1])],
        "x": {"label": image.x.label, "unit": image.x.unit},
        "y": {"label": image.y.label, "unit": image.y.unit},
        "z": {"label": image.z.label, "unit": image.z.unit},
    }


def _downsample(x: np.ndarray, y: np.ndarray, max_points: int) -> list[list[float]]:
    """Min/max decimation — preserves spectral peaks while bounding transport size."""
    n = len(x)
    if n <= max_points:
        return [[float(xi), float(yi)] for xi, yi in zip(x, y, strict=False)]
    bucket = max(1, n // (max_points // 2))
    points: list[list[float]] = []
    for i in range(0, n, bucket):
        xs, ys = x[i:i + bucket], y[i:i + bucket]
        if len(ys) == 0:
            continue
        lo, hi = int(np.argmin(ys)), int(np.argmax(ys))
        for j in sorted({lo, hi}):
            points.append([float(xs[j]), float(ys[j])])
    return points
