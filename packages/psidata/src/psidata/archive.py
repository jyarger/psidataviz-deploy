"""Read datasets packaged inside a ``.zip`` archive.

Cases handled (no ``nmrglue`` dependency):

* **Magritek SpinSolve** export — contains ``spectrum_processed.csv`` (``Frequency(ppm),Intensity``),
  a ready processed spectrum.
* **Bruker TopSpin** dataset — ``…/pdata/N/1r`` (int32 processed real spectrum) + ``procs``; the ppm
  axis is rebuilt from ``SI`` / ``SW_p`` / ``SF`` / ``OFFSET`` and intensities scaled by ``2**NC_proc``.
* **Zipped single data file** (e.g. ``…CPMG.txt.zip``) — extract the data member and route it to the
  normal reader registry.

macOS ``__MACOSX`` resource-fork entries are ignored.
"""

from __future__ import annotations

import bz2
import gzip
import io
import lzma
import os
import re
import tarfile
import zipfile

import numpy as np
import pandas as pd

from .model import Axis, Dataset, Image2D, Signal, SourceInfo
from .readers._tabular import parse_numeric_table
from .readers.base import Candidate
from .readers.nmr_jcamp import NMRMetadata
from .registry import DETECT_THRESHOLD, read, score_readers

_BRUKER_MARKERS = {"acqus", "acqu", "fid", "ser", "pulseprogram", "procs"}
_MAX_ZIP_DEPTH = 3  # guard against deeply-nested or self-referential archives

# tarball suffixes (handled by repackaging into a zip so the whole zip pipeline applies unchanged)
_TAR_SUFFIXES = (".tar.bz2", ".tbz2", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar")
_SINGLE_SUFFIXES = (".bz2", ".gz", ".xz")  # a single compressed file (no tar wrapper)


def is_archive(name: str) -> bool:
    """True for any archive/compressed container we can unwrap (zip, tarball, or a single .bz2/.gz/.xz)."""
    low = name.lower()
    return low.endswith(".zip") or low.endswith(_TAR_SUFFIXES) or low.endswith(_SINGLE_SUFFIXES)


def _tar_to_zip(content: bytes) -> bytes:
    """Repackage a tarball (any compression) into an in-memory zip, reusing all the zip logic below."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(content)) as tf, \
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for member in tf.getmembers():
            if member.isfile():
                extracted = tf.extractfile(member)
                if extracted is not None:
                    zf.writestr(member.name, extracted.read())
    return buf.getvalue()


def _decompress_single(filename: str, content: bytes) -> tuple[str, bytes]:
    """Decompress a single .bz2/.gz/.xz file and return (inner_filename, bytes)."""
    low = filename.lower()
    if low.endswith(".bz2"):
        return filename[:-4], bz2.decompress(content)
    if low.endswith(".gz"):
        return filename[:-3], gzip.decompress(content)
    if low.endswith(".xz"):
        return filename[:-3], lzma.decompress(content)
    return filename, content


def read_archive(filename: str, content: bytes, *, technique_hint: str | None = None,
                 member: str | None = None) -> Dataset:
    """Parse a dataset from any supported archive — zip, tarball (``.tar.bz2``/``.tar.gz``/…), or a
    single compressed file — into the universal model. Tarballs reuse the full zip pipeline."""
    low = filename.lower()
    if low.endswith(_TAR_SUFFIXES):
        return read_zip(filename, _tar_to_zip(content), technique_hint=technique_hint, member=member)
    if low.endswith(_SINGLE_SUFFIXES):
        inner, data = _decompress_single(filename, content)
        return read(Candidate(filename=inner, content=data, technique_hint=technique_hint))
    return read_zip(filename, content, technique_hint=technique_hint, member=member)


def archive_datasets(filename: str, content: bytes, *,
                     technique_hint: str | None = None) -> list[dict]:
    """List the distinct datasets inside an archive (for the multi-dataset selector). A single
    compressed file holds one dataset, so it returns ``[]`` (load it directly with read_archive)."""
    low = filename.lower()
    if low.endswith(_TAR_SUFFIXES):
        return zip_datasets(filename, _tar_to_zip(content), technique_hint=technique_hint)
    if low.endswith(_SINGLE_SUFFIXES):
        return []
    return zip_datasets(filename, content, technique_hint=technique_hint)


class ArchiveError(Exception):
    """Raised when an archive can't be turned into a dataset (empty, unknown, or unreadable)."""


def _members(zf: zipfile.ZipFile) -> list[str]:
    return [m for m in zf.namelist() if not m.endswith("/") and "__MACOSX" not in m]


def looks_like_bruker(members: list[str]) -> bool:
    return bool({os.path.basename(m) for m in members} & _BRUKER_MARKERS)


def _find(members: list[str], suffix: str) -> str | None:
    return next((m for m in members if m.endswith(suffix)), None)


def read_zip(filename: str, content: bytes, *, technique_hint: str | None = None,
             member: str | None = None, _depth: int = 0) -> Dataset:
    """Parse a dataset contained in a zip archive's bytes into the universal model.

    A common upload pattern is to zip together *several formats of the same dataset* (and sometimes to
    nest a zip inside a zip). We first handle the assembled multi-file vendor exports (SpinSolve, Bruker),
    then pick the **most-confidently-parseable** member using the full reader registry — so a zip holding
    only a Bruker OPUS ``.0`` or a structure file parses just like one holding a ``.csv`` — and recurse
    into a nested ``.zip`` when that is the best (or only) candidate. When a zip holds *several distinct
    datasets*, :func:`zip_datasets` lists them and ``member`` selects which one to parse.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"{filename}: not a valid zip archive ({exc})") from exc

    members = _members(zf)
    if not members:
        raise ArchiveError(f"{filename}: archive is empty")

    if member is not None:  # caller chose a specific dataset inside a multi-dataset zip
        if member.endswith("/2rr"):
            return _read_bruker_2d(zf, member, filename, technique_hint)
        if member.endswith("/1r"):
            return _read_bruker(zf, member, filename, technique_hint)
        if member not in members:
            raise ArchiveError(f"{filename}: member {member!r} not found in archive")
        return _read_member(zf, member, filename, technique_hint, _depth)

    spinsolve = _find(members, "spectrum_processed.csv") or _find(members, "spectrum.csv")
    if spinsolve:
        return _read_spinsolve(zf, spinsolve, filename, technique_hint)

    if looks_like_bruker(members):
        experiments = _bruker_experiments(zf, members)
        if experiments:  # the first experiment (numbered subfolders -> use the bundle to pick others)
            path, _label = experiments[0]
            reader = _read_bruker_2d if path.endswith("/2rr") else _read_bruker
            return reader(zf, path, filename, technique_hint)
        raise ArchiveError(
            f"{filename}: Bruker archive without processed data (expected pdata/N/1r or 2rr + procs)."
        )

    pick = _best_member(zf, members, technique_hint)
    if pick is None:
        raise ArchiveError(f"{filename}: no recognized data file inside (members: {members[:5]})")
    kind, chosen, _score = pick
    return _read_member(zf, chosen, filename, technique_hint, _depth, kind=kind)


def _read_member(zf: zipfile.ZipFile, member: str, filename: str, technique_hint: str | None,
                 depth: int, kind: str = "file") -> Dataset:
    """Parse one member of a zip — recursing if it is itself a nested archive."""
    data = zf.read(member)
    if kind == "zip" or member.lower().endswith(".zip"):
        if depth >= _MAX_ZIP_DEPTH:
            raise ArchiveError(f"{filename}: nested archives too deep (> {_MAX_ZIP_DEPTH})")
        return read_zip(member, data, technique_hint=technique_hint, _depth=depth + 1)
    # uri carries the full member path (e.g. "run/ba_1.D/DAD1.CSV") so readers can recover folder context
    return read(Candidate(filename=os.path.basename(member), content=data,
                          uri=member, technique_hint=technique_hint))


def zip_datasets(filename: str, content: bytes, *, technique_hint: str | None = None) -> list[dict]:
    """List the *distinct datasets* inside a zip (one entry per dataset, with the member to load).

    A vendor multi-file export (Bruker/SpinSolve) is **one** dataset. Otherwise members are grouped by
    folder + base name (so the several formats of one measurement collapse), and only groups with a
    parseable member become datasets. Each entry: ``{"key", "member", "formats"}``. Used to expand a zip
    that bundles several datasets into selectable items; a single-dataset zip returns one entry.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return []
    members = _members(zf)
    if not members:
        return []
    if _find(members, "spectrum_processed.csv") or _find(members, "spectrum.csv"):
        return [{"key": _stem(filename), "member": None, "formats": _exts(members)}]
    if looks_like_bruker(members):
        experiments = _bruker_experiments(zf, members)
        if len(experiments) > 1:  # numbered subfolders -> one selectable dataset per experiment
            return [{"key": label, "member": path,
                     "formats": ["2rr" if path.endswith("/2rr") else "1r"]}
                    for path, label in experiments]
        return [{"key": _stem(filename), "member": None, "formats": _exts(members)}]

    groups: dict[tuple[str, str], list[str]] = {}
    for m in members:
        groups.setdefault((os.path.dirname(m), _stem(m)), []).append(m)
    datasets: list[dict] = []
    for (_dir, base), group_members in sorted(groups.items()):
        pick = _best_member(zf, group_members, technique_hint)
        # only confidently-parseable groups count as datasets (skip notes / previews / junk)
        if pick is None or (pick[0] != "zip" and pick[2] < DETECT_THRESHOLD):
            continue
        datasets.append({"key": _dataset_key(pick[1], base), "member": pick[1],
                         "formats": _exts(group_members)})
    return datasets


def _dataset_key(member: str, stem: str) -> str:
    """A human label for a dataset inside an archive — the run folder when the filename is a generic
    instrument export (e.g. an Agilent ``ba_1.D/DAD1.CSV`` lists as ``ba_1``, not ``DAD1``)."""
    parent = os.path.basename(os.path.dirname(member))
    if parent.lower().endswith(".d"):  # Agilent ChemStation run folder
        return parent[:-2]
    if stem.lower() in ("dad1", "dad", "spectrum", "spectrum_processed", "data", "fid", "1r") and parent:
        return parent
    return stem


def _exts(members: list[str]) -> list[str]:
    return sorted({os.path.splitext(m)[1].lstrip(".").lower() for m in members if os.path.splitext(m)[1]})


def _best_member(zf: zipfile.ZipFile, members: list[str],
                 technique_hint: str | None) -> tuple[str, str, float] | None:
    """Choose the member to parse: the one the registry is most confident about (ties → largest), or a
    nested zip if no member is directly parseable. Returns ``(kind, member, score)`` with kind
    ``"file"``/``"zip"`` (a nested zip scores 1.0); ``None`` if nothing is recognizable at all."""
    best: tuple[float, int, str] | None = None  # (score, size, member)
    nested = [m for m in members if m.lower().endswith(".zip")]
    for m in members:
        if m.lower().endswith(".zip"):
            continue  # considered only as a fallback, via recursion
        try:
            content = zf.read(m)
        except (KeyError, RuntimeError):
            continue
        cand = Candidate(filename=os.path.basename(m), content=content, technique_hint=technique_hint)
        scored = score_readers(cand)
        score = scored[0][1] if scored else 0.0
        key = (score, zf.getinfo(m).file_size, m)
        if best is None or key > best:
            best = key
    if best and best[0] >= DETECT_THRESHOLD:
        return ("file", best[2], best[0])
    if nested:  # nothing parses directly, but there's an inner archive — recurse into the largest
        return ("zip", max(nested, key=lambda m: zf.getinfo(m).file_size), 1.0)
    if best and best[0] > 0:  # a member matched weakly; let read() try and raise a clear error
        return ("file", best[2], best[0])
    return None  # nothing recognizable


# --- SpinSolve ---------------------------------------------------------------------------------
def _read_spinsolve(zf: zipfile.ZipFile, member: str, filename: str,
                    technique_hint: str | None) -> Dataset:
    table = parse_numeric_table(zf.read(member).decode("utf-8", "replace"))
    if table.empty or table.shape[1] < 2:
        raise ArchiveError(f"{filename}: SpinSolve spectrum CSV had no (ppm, intensity) data")
    par = _member_text(zf, "acqu.par")
    kv = dict(re.findall(r'(\w+)\s*=\s*"?([^"\n]+?)"?\s*$', par, re.M)) if par else {}
    meta = NMRMetadata(sample_name=kv.get("Sample") or _stem(filename), solvent=kv.get("Solvent"),
                       frequency_mhz=_float(kv.get("b1Freq")),
                       data_type="NMR processed spectrum (SpinSolve)", npoints=len(table))
    return _nmr_dataset(filename, technique_hint, "nmr_spinsolve_zip",
                        _nmr_signal(table["col0"], table["col1"]), meta)


# --- Bruker ------------------------------------------------------------------------------------
def _read_bruker(zf: zipfile.ZipFile, oner: str, filename: str,
                 technique_hint: str | None) -> Dataset:
    procs = zf.read(_sibling(oner, "procs")).decode("latin1")
    si = int(float(_par(procs, "SI") or 0))
    raw = zf.read(oner)
    if not si:
        si = len(raw) // 4
    bytord = int(float(_par(procs, "BYTORDP") or 0))
    nc = int(float(_par(procs, "NC_proc") or 0))
    y = np.frombuffer(raw[: si * 4], dtype=(">" if bytord else "<") + "i4").astype(float) * 2.0**nc

    sw_p, sf, offset = _float(_par(procs, "SW_p")), _float(_par(procs, "SF")), _float(_par(procs, "OFFSET"))
    if sw_p and sf and offset is not None and si:
        ppm = offset - np.arange(si) * (sw_p / sf) / si  # point 0 = left edge (OFFSET), decreasing
    else:
        ppm = np.arange(si)[::-1].astype(float)

    title = _member_text_exact(zf, _sibling(oner, "title"))
    sample = (title.strip().splitlines()[0].strip() if title and title.strip() else "") or _stem(filename)
    meta = NMRMetadata(sample_name=sample, frequency_mhz=sf,
                       data_type="NMR processed spectrum (Bruker)", npoints=len(y))
    return _nmr_dataset(filename, technique_hint, "nmr_bruker_zip", _nmr_signal(ppm, y), meta)


# --- multi-experiment Bruker zips (numbered subfolders 1/, 2/, … each a separate experiment) -----
_PULPROG_NAMES = (
    ("hsqc", "HSQC"), ("hmbc", "HMBC"), ("h2bc", "H2BC"), ("hmqc", "HMQC"), ("cosy", "COSY"),
    ("noesy", "NOESY"), ("roesy", "ROESY"), ("tocsy", "TOCSY"), ("jres", "J-res"), ("dept", "DEPT"),
)


def _proc_key(path: str) -> int:
    m = re.search(r"/pdata/(\d+)/", path)
    return int(m.group(1)) if m else 0


def _prefer_proc1(paths: list[str]) -> str:
    return next((p for p in paths if "/pdata/1/" in p), min(paths, key=_proc_key))


def _bruker_nuclei(acqus: str) -> tuple[str, str]:
    """The direct (F2) and indirect (F1) nuclei. Bruker sets ``NUC2=off`` for homonuclear experiments,
    where the indirect dimension shares the observed nucleus."""
    nuc1 = (_par(acqus, "NUC1") or "").strip("<>")
    nuc2 = (_par(acqus, "NUC2") or "").strip("<>")
    if nuc2.lower() in ("off", "", "none"):
        nuc2 = nuc1
    return nuc1, nuc2


def _bruker_label(zf: zipfile.ZipFile, expdir: str, mset: set[str], *, is_2d: bool) -> str:
    acqus = zf.read(f"{expdir}/acqus").decode("latin1", "replace") if f"{expdir}/acqus" in mset else ""
    pulprog = (_par(acqus, "PULPROG") or "").lower().strip("<>")
    for key, name in _PULPROG_NAMES:
        if key in pulprog:
            return name
    nuc1, nuc2 = _bruker_nuclei(acqus)
    if is_2d:
        return f"{nuc2 or 'F1'}-{nuc1 or 'F2'} 2D"
    return nuc1 or "1D"


def _bruker_experiments(zf: zipfile.ZipFile, members: list[str]) -> list[tuple[str, str]]:
    """The processed experiments in a Bruker zip — one per numbered experiment folder, each as
    ``(data_path, label)``. Picks 2D (``2rr``) data when present, else 1D (``1r``); prefers ``pdata/1``."""
    mset = set(members)
    by_exp: dict[str, list[str]] = {}
    for m in members:
        if "/pdata/" in m and os.path.basename(m) in ("1r", "2rr"):
            by_exp.setdefault(m.split("/pdata/")[0], []).append(m)

    out: list[tuple[str, str]] = []
    seen: dict[str, int] = {}
    for expdir in sorted(by_exp, key=lambda d: (0, int(t)) if (t := d.rsplit("/", 1)[-1]).isdigit() else (1, t)):
        paths = by_exp[expdir]
        two_d = [p for p in paths if p.endswith("/2rr")]
        chosen = _prefer_proc1(two_d) if two_d else _prefer_proc1([p for p in paths if p.endswith("/1r")])
        pdir = chosen.rsplit("/", 1)[0]
        needed = ("procs", "proc2s") if chosen.endswith("/2rr") else ("procs",)
        if any(f"{pdir}/{n}" not in mset for n in needed):
            continue  # missing proc parameters -> can't decode
        label = _bruker_label(zf, expdir, mset, is_2d=chosen.endswith("/2rr"))
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:  # disambiguate duplicate experiment types by experiment number
            label = f"{label} ({expdir.rsplit('/', 1)[-1]})"
        out.append((chosen, label))
    return out


def _detile(raw: np.ndarray, si1: int, si2: int, xd1: int, xd2: int) -> np.ndarray:
    """Reassemble a Bruker 2D processed matrix from its submatrix (XDIM) tiling into a full grid."""
    if raw.size < si1 * si2:
        raw = np.pad(raw, (0, si1 * si2 - raw.size))
    if xd1 >= si1 and xd2 >= si2:
        return raw[: si1 * si2].reshape(si1, si2)
    grid = np.zeros((si1, si2))
    t = 0
    for i1 in range(si1 // xd1):
        for i2 in range(si2 // xd2):
            grid[i1 * xd1:(i1 + 1) * xd1, i2 * xd2:(i2 + 1) * xd2] = raw[t:t + xd1 * xd2].reshape(xd1, xd2)
            t += xd1 * xd2
    return grid


def _bruker_ppm(proc_text: str, n: int) -> np.ndarray | None:
    sw_p, sf, offset = _float(_par(proc_text, "SW_p")), _float(_par(proc_text, "SF")), _float(_par(proc_text, "OFFSET"))
    if sw_p and sf and offset is not None and n:
        return offset - np.arange(n) * (sw_p / sf) / n
    return None


def _read_bruker_2d(zf: zipfile.ZipFile, twrr: str, filename: str,
                    technique_hint: str | None) -> Dataset:
    """Decode a Bruker 2D processed spectrum (``pdata/N/2rr`` + ``procs``/``proc2s``) into a contour
    map with ppm axes — F2 (direct, columns) from ``procs``, F1 (indirect, rows) from ``proc2s``."""
    pdir = twrr.rsplit("/", 1)[0]
    procs = zf.read(f"{pdir}/procs").decode("latin1")
    proc2s = zf.read(f"{pdir}/proc2s").decode("latin1")
    si2, si1 = int(float(_par(procs, "SI") or 0)), int(float(_par(proc2s, "SI") or 0))
    if not (si1 and si2):
        raise ArchiveError(f"{filename}: Bruker 2rr missing SI dimensions")
    xd2 = int(float(_par(procs, "XDIM") or si2)) or si2
    xd1 = int(float(_par(proc2s, "XDIM") or si1)) or si1
    bytord = int(float(_par(procs, "BYTORDP") or 0))
    nc = int(float(_par(procs, "NC_proc") or 0))
    raw = np.frombuffer(zf.read(twrr), dtype=(">" if bytord else "<") + "i4").astype(float) * 2.0**nc
    grid = _detile(raw, si1, si2, xd1, xd2)

    expdir = twrr.split("/pdata/")[0]
    acqus = _member_text_exact(zf, f"{expdir}/acqus") or ""
    nuc1, nuc2 = _bruker_nuclei(acqus)  # direct (F2, columns/x), indirect (F1, rows/y)
    x_ppm, y_ppm = _bruker_ppm(procs, si2), _bruker_ppm(proc2s, si1)
    image = Image2D(
        name=_stem(filename), data=grid,
        x=Axis(label=f"{nuc1} F2".strip(), unit="ppm" if x_ppm is not None else None, quantity="chemical_shift"),
        y=Axis(label=f"{nuc2} F1".strip(), unit="ppm" if y_ppm is not None else None, quantity="chemical_shift"),
        z=Axis(label="Intensity", unit="a.u.", quantity="intensity"),
        kind="nmr2d", x_values=x_ppm, y_values=y_ppm,
    )
    title = _member_text_exact(zf, _sibling(twrr, "title"))
    sample = (title.strip().splitlines()[0].strip() if title and title.strip() else "") or _stem(filename)
    meta = NMRMetadata(sample_name=sample, nucleus=nuc1 or None,
                       data_type="2D NMR processed spectrum (Bruker)")
    meta.experiment = f"{nuc2}-{nuc1} 2D" if (nuc1 and nuc2) else "2D NMR"
    meta.dimensions = f"{si1} × {si2}"
    return Dataset(
        technique=technique_hint or "NMR",
        source=SourceInfo(uri=filename, filename=os.path.basename(filename),
                          reader="nmr_bruker_zip", reader_version="0.1.0"),
        metadata=meta, images=[image],
    )


# --- shared helpers ----------------------------------------------------------------------------
def _nmr_signal(ppm, intensity) -> Signal:
    frame = pd.DataFrame({"Chemical shift": np.asarray(ppm, float),
                          "Intensity": np.asarray(intensity, float)})
    return Signal(name="spectrum",
                  x=Axis(label="Chemical shift", unit="ppm", quantity="chemical_shift"),
                  y=Axis(label="Intensity", unit="a.u.", quantity="intensity"),
                  frame=frame)


def _nmr_dataset(filename: str, technique_hint: str | None, reader: str, signal: Signal,
                 meta: NMRMetadata) -> Dataset:
    return Dataset(
        technique=technique_hint or "NMR",
        source=SourceInfo(uri=filename, filename=os.path.basename(filename),
                          reader=reader, reader_version="0.1.0"),
        metadata=meta, signals=[signal],
    )


def _sibling(member: str, name: str) -> str:
    return member.rsplit("/", 1)[0] + "/" + name if "/" in member else name


def _member_text(zf: zipfile.ZipFile, basename: str) -> str | None:
    m = _find(_members(zf), basename)
    return zf.read(m).decode("latin1") if m else None


def _member_text_exact(zf: zipfile.ZipFile, path: str) -> str | None:
    try:
        return zf.read(path).decode("latin1")
    except KeyError:
        return None


def _par(text: str, key: str) -> str | None:
    m = re.search(rf"##\$\s*{key}=\s*(.*)", text)
    return m.group(1).strip() if m else None


def _float(s: str | None) -> float | None:
    try:
        return float(s) if s not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _stem(filename: str) -> str:
    return os.path.splitext(os.path.basename(filename))[0]
