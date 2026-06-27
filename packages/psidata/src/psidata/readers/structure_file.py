"""Reader for 3D molecular / crystal **structure files** (``.xyz`` ``.mol`` ``.sdf`` ``.pdb`` ``.mol2`` ``.cif``).

A structure is carried as the **raw file text plus a format string** and rendered client-side by 3Dmol.js,
which already parses all of these — so this reader does only light validation and a cheap atom count, and
produces a :class:`Dataset` whose ``structure`` is set (no 1D signals).
"""

from __future__ import annotations

from ..model import Dataset, Metadata, SourceInfo, Structure3D
from ..registry import register_reader
from .base import BaseReader, Candidate

# file extension -> 3Dmol.js parser format (a single MDL .mol is read by the sdf/molblock parser)
_FORMATS = {".xyz": "xyz", ".mol": "sdf", ".sdf": "sdf", ".pdb": "pdb", ".mol2": "mol2", ".cif": "cif"}


@register_reader
class StructureFileReader(BaseReader):
    technique = "Computational"
    name = "structure_file"
    version = "0.1.0"
    extensions = tuple(_FORMATS)

    def sniff(self, candidate: Candidate) -> float:
        ext = candidate.ext
        if ext not in _FORMATS:
            return 0.0
        head = candidate.head(2000)
        if ext == ".xyz":
            for line in head.splitlines():
                s = line.strip()
                if s:  # the first non-blank line of an XYZ file is the integer atom count
                    return 0.8 if s.isdigit() else 0.0
            return 0.0
        if ext in (".mol", ".sdf"):
            return 0.85 if ("V2000" in head or "V3000" in head or "M  END" in head) else 0.45
        if ext == ".pdb":
            return 0.85 if any(line.startswith(("ATOM", "HETATM", "HEADER", "CRYST1"))
                               for line in head.splitlines()) else 0.3
        if ext == ".mol2":
            return 0.85 if "@<TRIPOS>" in head else 0.3
        if ext == ".cif":
            low = head.lower()
            return 0.8 if ("_cell_" in low or "_atom_site" in low or "loop_" in low) else 0.3
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        text = candidate.as_text()
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=Metadata(sample_name=candidate.stem),
            structure=Structure3D(data=text, fmt=_FORMATS[candidate.ext], title=candidate.stem,
                                  n_atoms=_count_atoms(candidate.ext, text)),
        )


def _count_atoms(ext: str, text: str) -> int | None:
    try:
        if ext == ".xyz":
            for line in text.splitlines():
                if line.strip():
                    return int(line.strip())
        elif ext in (".mol", ".sdf"):
            lines = text.splitlines()
            if len(lines) >= 4:  # the V2000 "counts" line is line 4; first 3 chars = atom count
                return int(lines[3][:3])
        elif ext == ".pdb":
            return sum(1 for ln in text.splitlines() if ln.startswith(("ATOM", "HETATM")))
    except (ValueError, IndexError):
        return None
    return None
