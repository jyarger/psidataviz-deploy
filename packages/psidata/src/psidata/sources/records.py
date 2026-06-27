"""Group files into *data records* — one scientific dataset, possibly saved in several formats.

Labs routinely save the same measurement under one base name in multiple files: e.g. DSC as
``…Tzero.txt`` (tab text) **and** ``…Tzero.xls`` (Excel) **and** ``…Tzero.tri`` (Trios binary);
FTIR as ``…silk.dpt`` (ASCII) **and** ``…silk.0`` (Bruker OPUS binary); Raman as ``…Pos_6.csv``
(the spectrum) **and** ``…Pos_6_spec.txt`` (instrument parameters — *not* data).

This module collapses those into a :class:`DataRecord` with one :class:`FormatVariant` per file,
classifying each format (data / binary-original / spreadsheet / sidecar / image) and picking the
best *parseable* variant for visualization. It turns "N files" into "one dataset in M formats."
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ..filename import ParsedName, parse_filename
from .base import FileRef
from .catalog import CatalogEntry, compound_for

# --- format roles -----------------------------------------------------------------------------
DATA = "data"                  # ASCII/text the readers can (or could) parse
BINARY_ORIGINAL = "binary_original"  # native instrument file (source of truth, not yet parseable)
SPREADSHEET = "spreadsheet"
SIDECAR = "sidecar"            # metadata/parameters next to the data (e.g. Raman _spec.txt)
IMAGE = "image"
ARCHIVE = "archive"
DOCUMENT = "document"
OTHER = "other"

_SIDECAR_STEM = re.compile(r"_spec$", re.IGNORECASE)

# Preference order when several parseable data formats exist (best first).
# Prefer parseable ASCII variants; a packaged `.zip` is the lowest-priority primary (used when it's
# the only parseable variant, e.g. a zipped Bruker/SpinSolve NMR dataset).
# preferred primary data format (earlier = better); a calc OUTPUT (.log/.out) beats its INPUT (.gjf/.inp)
_PRIMARY_PREFERENCE = (".csv", ".txt", ".dpt", ".asc", ".dx", ".jdx", ".tsv", ".dat", ".log", ".out", ".zip")


@dataclass(frozen=True)
class FormatInfo:
    role: str
    label: str
    is_data: bool  # does this file contain the scientific data itself (even if not yet parseable)?


_EXT_TABLE: dict[str, FormatInfo] = {
    ".csv": FormatInfo(DATA, "Comma-delimited text", True),
    ".txt": FormatInfo(DATA, "Tab/space-delimited text", True),
    ".tsv": FormatInfo(DATA, "Tab-separated text", True),
    ".dat": FormatInfo(DATA, "ASCII data", True),
    ".dta": FormatInfo(DATA, "Gamry electrochemistry (text)", True),
    ".dcs": FormatInfo(DATA, "Circular-dichroism spectrum (text)", True),
    ".dpt": FormatInfo(DATA, "Bruker data-point table (ASCII)", True),
    ".asc": FormatInfo(DATA, "ASCII spectrum", True),
    ".dx": FormatInfo(DATA, "JCAMP-DX (ASCII)", True),
    ".jdx": FormatInfo(DATA, "JCAMP-DX (ASCII)", True),
    ".tri": FormatInfo(BINARY_ORIGINAL, "TA Trios native (binary)", True),
    ".sp": FormatInfo(BINARY_ORIGINAL, "PerkinElmer native (binary)", True),
    ".spa": FormatInfo(BINARY_ORIGINAL, "Thermo Scientific native (binary)", True),
    ".spe": FormatInfo(BINARY_ORIGINAL, "Spectrum native (binary)", True),
    ".fid": FormatInfo(BINARY_ORIGINAL, "Bruker NMR native (binary)", True),
    ".ser": FormatInfo(BINARY_ORIGINAL, "Bruker NMR native (binary)", True),
    ".xrdml": FormatInfo(DATA, "PANalytical XRD (XML)", True),
    ".udf": FormatInfo(DATA, "Philips XRD (text)", True),
    ".edf": FormatInfo(DATA, "ESRF detector image", True),
    ".img": FormatInfo(DATA, "ADSC / d*TREK detector image", True),
    ".mccd": FormatInfo(DATA, "MarCCD detector image", True),
    ".h5": FormatInfo(DATA, "HDF5 / NeXus data", True),
    ".hdf5": FormatInfo(DATA, "HDF5 / NeXus data", True),
    ".gjf": FormatInfo(DATA, "Gaussian input (geometry)", True),
    ".com": FormatInfo(DATA, "Gaussian input (geometry)", True),
    ".inp": FormatInfo(DATA, "Computational input (geometry)", True),
    ".xyz": FormatInfo(DATA, "XYZ molecular geometry", True),
    ".mol": FormatInfo(DATA, "MDL molfile (structure)", True),
    ".sdf": FormatInfo(DATA, "SDF structure", True),
    ".pdb": FormatInfo(DATA, "PDB structure", True),
    ".mol2": FormatInfo(DATA, "Tripos MOL2 structure", True),
    ".cif": FormatInfo(DATA, "Crystallographic CIF", True),
    ".xls": FormatInfo(SPREADSHEET, "Excel spreadsheet", True),
    ".xlsx": FormatInfo(SPREADSHEET, "Excel spreadsheet", True),
    ".zip": FormatInfo(ARCHIVE, "Compressed archive", True),
    ".bz2": FormatInfo(ARCHIVE, "Compressed archive (tar.bz2)", True),
    ".gz": FormatInfo(ARCHIVE, "Compressed archive (tar.gz)", True),
    ".tgz": FormatInfo(ARCHIVE, "Compressed archive (tar.gz)", True),
    ".tbz2": FormatInfo(ARCHIVE, "Compressed archive (tar.bz2)", True),
    ".xz": FormatInfo(ARCHIVE, "Compressed archive (tar.xz)", True),
    ".tar": FormatInfo(ARCHIVE, "Tar archive", True),
    ".jpg": FormatInfo(IMAGE, "Image / preview", False),
    ".jpeg": FormatInfo(IMAGE, "Image / preview", False),
    ".png": FormatInfo(IMAGE, "Image / preview", False),
    ".gif": FormatInfo(IMAGE, "Image / preview", False),
    ".bmp": FormatInfo(IMAGE, "Image / preview", False),
    ".svg": FormatInfo(IMAGE, "Vector image", False),
    ".dm3": FormatInfo(IMAGE, "Gatan DigitalMicrograph (TEM)", True),
    ".dm4": FormatInfo(IMAGE, "Gatan DigitalMicrograph (TEM)", True),
    ".tif": FormatInfo(IMAGE, "Image (TIFF)", False),
    ".tiff": FormatInfo(IMAGE, "Image (TIFF)", False),
    ".pdf": FormatInfo(DOCUMENT, "PDF document", False),
}


def classify_format(filename: str) -> FormatInfo:
    """Classify a single file by its name/extension (no content read)."""
    base = os.path.basename(filename).lower()
    stem, ext = os.path.splitext(base)
    if ext == ".txt" and _SIDECAR_STEM.search(stem):
        return FormatInfo(SIDECAR, "Instrument acquisition parameters", False)
    if ext in _EXT_TABLE:
        return _EXT_TABLE[ext]
    if ext[1:].isdigit():  # numeric extensions: Bruker OPUS (name.0..name.9) or TA TGA native (name.001)
        label = "Bruker OPUS native (binary)" if len(ext) == 2 else "Instrument native (binary)"
        return FormatInfo(BINARY_ORIGINAL, label, True)
    return FormatInfo(OTHER, f"{ext or 'no-extension'} file", False)


def record_key(filename: str) -> str:
    """Normalized base name used to group format variants (strips known sidecar/tarball suffixes)."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    if stem.lower().endswith(".tar"):  # e.g. "foo.tar.bz2" -> stem "foo.tar" -> "foo"
        stem = stem[:-4]
    return _SIDECAR_STEM.sub("", stem)


@dataclass
class FormatVariant:
    file: FileRef
    info: FormatInfo
    reader_name: str | None = None  # set only when a registered reader can parse this data file

    @property
    def ext(self) -> str:
        return self.file.ext

    @property
    def parseable(self) -> bool:
        return self.reader_name is not None

    def as_dict(self) -> dict:
        return {
            "name": self.file.name,
            "ext": self.ext,
            "role": self.info.role,
            "label": self.info.label,
            "is_data": self.info.is_data,
            "parseable": self.parseable,
            "reader": self.reader_name,
            "size": self.file.size,
            "download_url": self.file.download_url,
        }


@dataclass
class DataRecord:
    key: str            # normalized stem (the dataset's base name)
    technique: str
    parsed: ParsedName
    variants: list[FormatVariant]

    @property
    def data_variants(self) -> list[FormatVariant]:
        # a parseable variant is data even if statically classed otherwise (e.g. a detector .tif)
        return [v for v in self.variants if v.info.is_data or v.parseable]

    @property
    def parseable_variants(self) -> list[FormatVariant]:
        return [v for v in self.variants if v.parseable]

    @property
    def sidecars(self) -> list[FormatVariant]:
        return [v for v in self.variants if v.info.role == SIDECAR]

    @property
    def uid(self) -> str:
        """A source-unique id: the base name plus its folder, since the same base name can recur in
        different sub-folders (e.g. ``min.pdb`` in several MD run directories)."""
        directory = os.path.dirname(self.variants[0].file.path) if self.variants else ""
        return f"{directory}/{self.key}" if directory else self.key

    @property
    def is_data_record(self) -> bool:
        """True if any variant holds scientific data (vs. image/preview/params only)."""
        return bool(self.data_variants)

    @property
    def primary(self) -> FormatVariant | None:
        """The best parseable data variant to visualize, or None if none is parseable yet."""
        cands = self.parseable_variants
        if not cands:
            return None
        return min(
            cands,
            key=lambda v: _PRIMARY_PREFERENCE.index(v.ext)
            if v.ext in _PRIMARY_PREFERENCE else len(_PRIMARY_PREFERENCE),
        )

    @property
    def supported(self) -> bool:
        return self.primary is not None

    @property
    def formats(self) -> list[str]:
        return sorted({v.ext for v in self.variants})

    @property
    def compound(self) -> str:
        """The chemical/sample this record is about, inferred from the folder or filename ("" if unknown)."""
        directory = os.path.dirname(self.variants[0].file.path) if self.variants else ""
        return compound_for(directory, self.key)

    def summary(self) -> dict:
        return {
            "key": self.key,
            "technique": self.technique,
            "compound": self.compound,
            "date": self.parsed.date.isoformat() if self.parsed.date else None,
            "description": self.parsed.description,
            "formats": self.formats,
            "n_variants": len(self.variants),
            "supported": self.supported,
            "primary": self.primary.ext if self.primary else None,
            "sidecars": [v.ext for v in self.sidecars],
            "variants": [v.as_dict() for v in self.variants],
        }


def build_records(entries: list[CatalogEntry]) -> list[DataRecord]:
    """Collapse catalog entries (one per file) into records (one per dataset, many formats)."""
    groups: dict[tuple[str, str], list[CatalogEntry]] = {}
    for entry in entries:
        directory = os.path.dirname(entry.file.path)
        groups.setdefault((directory, record_key(entry.file.name)), []).append(entry)

    records: list[DataRecord] = []
    for (_directory, key), grouped in groups.items():
        technique = grouped[0].technique
        variants: list[FormatVariant] = []
        for entry in grouped:
            info = classify_format(entry.file.name)
            # A matched reader makes a file parseable (even a detector .tif statically classed as an
            # image) — but never a sidecar.
            reader = entry.reader_name if (entry.supported and info.role != SIDECAR) else None
            variants.append(FormatVariant(file=entry.file, info=info, reader_name=reader))
        variants.sort(key=lambda v: v.ext)
        records.append(DataRecord(key=key, technique=technique,
                                  parsed=parse_filename(key), variants=variants))

    records.sort(key=lambda r: (r.technique, r.parsed.date is None, r.parsed.date or _EPOCH, r.key))
    return records


# date sentinel for sorting records whose filename lacks a date
from datetime import date as _date  # noqa: E402

_EPOCH = _date(1900, 1, 1)
