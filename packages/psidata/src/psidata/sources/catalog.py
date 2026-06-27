"""Scan a :class:`DataSource` into a grouped, summarized catalog — cheaply, without downloads.

Files are grouped by their top-level folder (the lab convention: one folder per instrument/method),
enriched with filename-derived metadata (date, description), and flagged as ``supported`` when a
registered reader is likely to handle them. Full parsing happens later, on demand.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from ..archive import is_archive
from ..filename import ParsedName, parse_filename
from ..registry import get_readers
from .base import DataSource, FileRef

ROOT_GROUP = "(root)"

# Different labs/sources name the same technique folder differently (e.g. "IR" vs "FTIR").
# Map lowercase folder names to one canonical technique so they merge into a single group.
_TECHNIQUE_ALIASES = {
    "ir": "FTIR",
    "ft-ir": "FTIR",
    "ftir": "FTIR",
    "infrared": "FTIR",
    "uv": "UV-Vis",
    "uvvis": "UV-Vis",
    "uv-vis": "UV-Vis",
    "uv_vis": "UV-Vis",
    "uv-visible": "UV-Vis",
    "mass_spec": "Mass Spec",
    "massspec": "Mass Spec",
    "ms": "Mass Spec",
    "circular_dichroism": "CD",
}


def canonical_technique(top_dir: str) -> str:
    """Normalize a folder name to one canonical technique label (``IR`` → ``FTIR``, …)."""
    if not top_dir:
        return ROOT_GROUP
    return _TECHNIQUE_ALIASES.get(top_dir.strip().lower(), top_dir)


@dataclass(frozen=True)
class CatalogEntry:
    file: FileRef
    technique: str
    parsed: ParsedName
    supported: bool
    reader_name: str | None = None

    def as_dict(self) -> dict:
        return {
            "path": self.file.path,
            "name": self.file.name,
            "technique": self.technique,
            "date": self.parsed.date.isoformat() if self.parsed.date else None,
            "description": self.parsed.description,
            "ext": self.file.ext,
            "size": self.file.size,
            "supported": self.supported,
            "reader": self.reader_name,
            "download_url": self.file.download_url,
        }


@dataclass
class Catalog:
    source_label: str
    entries: list[CatalogEntry]

    def groups(self) -> dict[str, list[CatalogEntry]]:
        grouped: dict[str, list[CatalogEntry]] = defaultdict(list)
        for entry in self.entries:
            grouped[entry.technique].append(entry)
        return dict(sorted(grouped.items()))

    def techniques(self) -> list[str]:
        return sorted({e.technique for e in self.entries})

    def supported(self) -> list[CatalogEntry]:
        return [e for e in self.entries if e.supported]

    def records(self):
        """Collapse files into datasets: one :class:`DataRecord` per base name, many formats."""
        from .records import build_records  # local import avoids a circular dependency
        return build_records(self.entries)

    def record_groups(self) -> dict[str, list]:
        """Records grouped by technique (the dataset-centric view of the catalog)."""
        grouped: dict[str, list] = defaultdict(list)
        for record in self.records():
            grouped[record.technique].append(record)
        return dict(sorted(grouped.items()))

    def summary(self) -> dict:
        groups = self.groups()
        records = self.records()
        data_records = [r for r in records if r.is_data_record]
        return {
            "source": self.source_label,
            "n_files": len(self.entries),
            "n_supported": len(self.supported()),
            "n_records": len(records),
            "n_data_records": len(data_records),
            "n_supported_records": sum(r.supported for r in records),
            "groups": {
                tech: {
                    "n_files": len(items),
                    "n_supported": sum(e.supported for e in items),
                }
                for tech, items in groups.items()
            },
        }


def _match_reader(top_dir: str, ext: str):
    """Find a registered reader whose technique matches the folder and whose extension fits.

    A generic reader (``technique == "*"``, e.g. the spreadsheet reader) is used only as a fallback when
    no technique-specific reader matches.
    """
    folder = canonical_technique(top_dir).lower()
    generic = None
    for reader in get_readers():
        tech = reader.technique.lower()
        ext_ok = not reader.extensions or ext in reader.extensions
        if tech == "*":
            if ext_ok and generic is None:
                generic = reader
        elif ext_ok and (tech == folder or tech in folder or (folder in tech and folder)):
            return reader
    return generic


def _technique_has_reader(technique: str) -> bool:
    """True if a *technique-specific* reader handles this technique (generic readers don't count)."""
    folder = canonical_technique(technique).lower()
    return any(
        r.technique.lower() != "*" and (
            r.technique.lower() == folder or r.technique.lower() in folder
            or (folder and folder in r.technique.lower()))
        for r in get_readers()
    )


# Keyword -> technique, for sources organized by sample/compound (the top folder is the molecule,
# not the instrument), where the technique is encoded in the filename instead.
_TECHNIQUE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("FTIR", ("ftir", "_ir_", "_ir.", "atrir", "atr-ir", "infrared", "opus")),
    ("NMR", ("nmr", "bruker400", "bruker500", "spinsolve", "nmready", "mhz", "_1h", "_13c", "_31p",
             "_19f", "_15n")),
    ("Raman", ("raman",)),  # bare wavelengths (532nm…) are ambiguous (also Brillouin) — keep explicit
    ("DSC", ("dsc", "mdsc", "calorimetry", "trios", "cmin")),  # cmin = a °C/min ramp rate (e.g. 5Cmin)
    ("XRD", ("xrd", "pxrd", "saxs", "waxs", "giwaxs", "diffract")),
    ("UV-Vis", ("uvvis", "uv-vis", "uv_vis", "uv_visible")),
    ("TGA", ("tga", "thermogravimetric")),
)


def infer_technique(filename: str) -> str | None:
    """Guess the technique from a filename's keywords (for sample-organized sources)."""
    low = filename.lower()
    for technique, keywords in _TECHNIQUE_KEYWORDS:
        if any(kw in low for kw in keywords):
            return technique
    return None


# Tokens that mark the end of the compound part of a name (techniques, instruments, conditions, solvents).
_COMPOUND_STOP = {
    "ms", "sims", "dsc", "nmr", "ir", "ftir", "raman", "xrd", "pxrd", "saxs", "waxs", "hplc", "dad",
    "tga", "uv", "vis", "uvvis", "cd", "dielectric", "brillouin", "acoustic", "ea", "sem", "tem",
    "data", "spectrum", "sample", "raw", "pos", "neg", "blank", "std", "opt", "freq", "scan", "edit",
    "meoh", "etoh", "h2o", "thf", "dcm", "dmso", "acn", "mecn", "si",
    "xtal", "crystal", "cryst", "powder", "film", "soln", "solution", "neat", "bulk", "thin", "depol",
    "pol", "run", "test", "rep", "deg", "rt",
    # computational methods / basis sets / descriptors that follow the compound name
    "dft", "b3lyp", "hf", "mp2", "ccsd", "am1", "pm3", "wb97xd", "m06", "gaussian", "gaussian16",
    "orca", "psi4", "sp", "scf", "pcsseg", "conformer", "conformers", "tablet",
}
_DATE_PREFIX = re.compile(r"^\d{4}[-_]\d{2}[-_]\d{2}[-_]?")
_UNIT_SUFFIX = re.compile(r"(nm|mw|mg|ml|mm|cm|hz|mhz|kv|um|kev)$", re.IGNORECASE)


def guess_compound(name: str) -> str:
    """Best-effort compound/sample guess from a dataset name: the leading word tokens up to the first
    technique / instrument / condition token. Returns "" when nothing looks like a real compound."""
    stem = re.sub(r"\.[a-z0-9]+$", "", name, flags=re.IGNORECASE)
    stem = _DATE_PREFIX.sub("", stem)
    out: list[str] = []
    for tok in re.split(r"[_\-\s.]+", stem):
        if not tok:
            continue
        low = tok.lower()
        if low in _COMPOUND_STOP or any(c.isdigit() for c in tok) or _UNIT_SUFFIX.search(low):
            break
        out.append(tok)
    if not any(re.search(r"[a-zA-Z]{3,}", t) for t in out):
        return ""
    return " ".join(out)


def compound_for(directory: str, key: str) -> str:
    """The compound a record is about: the sample folder for sample-organized sources, otherwise guessed
    from the filename for instrument-organized ones."""
    top = directory.split("/")[0] if directory else ""
    if top and _technique_has_reader(canonical_technique(top)):
        return guess_compound(key)  # instrument-organized (folder is a technique) — compound is in the name
    if top:  # sample-organized: the top folder is the compound
        return top.replace("_", " ")
    return guess_compound(key)


# files that aren't datasets (don't let repo boilerplate skew the organization detection)
_NON_DATA = re.compile(r"^(readme|license|contributing|changelog|\.|index)", re.IGNORECASE)


def detect_organization(entries: list[CatalogEntry]) -> dict:
    """A first-pass read of how a source is laid out, so the user doesn't have to declare it:

    * **technique** — top folders are instruments/techniques (``Raman/``, ``NMR/`` …);
    * **sample** — top folders are compounds, with the technique encoded in the filename;
    * **unstructured** — files at the root or in folders we can't recognise as either.

    Returns the dominant ``kind`` plus the per-bucket counts (so the UI can report what it found and flag
    how many datasets it couldn't place)."""
    by_technique = by_sample = unstructured = 0
    for e in entries:
        if _NON_DATA.match(e.file.name):
            continue
        top = e.file.top_dir
        if not top:
            unstructured += 1
        elif _technique_has_reader(canonical_technique(top)):
            by_technique += 1
        elif infer_technique(e.file.name) or guess_compound(top):
            by_sample += 1
        else:
            unstructured += 1

    total = by_technique + by_sample + unstructured
    if total == 0:
        kind = "empty"
    elif by_technique >= 0.6 * total:
        kind = "technique"
    elif by_sample >= 0.6 * total:
        kind = "sample"
    elif unstructured >= 0.5 * total:
        kind = "unstructured"
    else:
        kind = "mixed"
    return {"kind": kind, "by_technique": by_technique, "by_sample": by_sample,
            "unstructured": unstructured, "total": total}


_SIMS_RE = re.compile(r"(?:^|[_\-. ])sims(?:$|[_\-. ])", re.IGNORECASE)


def _refine_subtechnique(technique: str, filename: str) -> str:
    """Split a coarse folder technique by filename when two methods share a folder. Mass-spec folders
    hold both standard MS and **secondary-ion MS (SIMS)** — a distinct surface technique."""
    if technique in ("Mass Spec", "SIMS") and _SIMS_RE.search(filename):
        return "SIMS"
    return technique


def build_entry(ref: FileRef) -> CatalogEntry:
    technique = canonical_technique(ref.top_dir)
    if not _technique_has_reader(technique):
        # sample-organized source (the top folder is a compound): infer technique from the filename
        technique = infer_technique(ref.name) or technique
    technique = _refine_subtechnique(technique, ref.name)
    reader = _match_reader(technique, ref.ext)
    supported = reader is not None
    reader_name = reader.name if reader else None
    # An archive (.zip or a .tar.bz2/.tar.gz tarball) is a packaged dataset (e.g. zipped Bruker/SpinSolve
    # NMR, or a tarball of Agilent .D runs); mark it supported when the technique has a reader, and let
    # `read_archive` unwrap/parse it on open.
    if is_archive(ref.name) and not supported and _technique_has_reader(technique):
        supported, reader_name = True, "archive"
    return CatalogEntry(
        file=ref,
        technique=technique,
        parsed=parse_filename(ref.name),
        supported=supported,
        reader_name=reader_name,
    )


def scan(source: DataSource) -> Catalog:
    """List a source and build a grouped, summarized catalog (no file contents fetched)."""
    entries = [build_entry(ref) for ref in source.list_files()]
    return Catalog(source_label=source.label, entries=entries)
