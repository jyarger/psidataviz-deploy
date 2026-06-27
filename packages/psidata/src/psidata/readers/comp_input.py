"""Reader for computational **input** files — Gaussian ``.gjf``/``.com`` and ORCA/general ``.inp``.

These hold the molecular geometry that was submitted to a calculation, so we extract it for the 3D
viewer (a structure-only :class:`Dataset`, like :mod:`structure_file`). Only **Cartesian** coordinates are
parsed — the longest contiguous run of ``Symbol x y z`` lines — which covers the common case; Z-matrix
(internal-coordinate) inputs and ``* xyzfile`` external references are not supported.
"""

from __future__ import annotations

import re

from ..model import Dataset, Metadata, SourceInfo, Structure3D
from ..registry import register_reader
from .base import BaseReader, Candidate

# an element symbol (optionally with an isotope/label digit) followed by exactly three decimal floats
_ATOM_RE = re.compile(
    r"^\s*([A-Za-z]{1,2})[0-9]*\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")


@register_reader
class CompInputReader(BaseReader):
    technique = "Computational"
    name = "comp_input"
    version = "0.1.0"
    extensions = (".gjf", ".com", ".inp")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        head = candidate.head(6000)
        atoms = sum(1 for ln in head.splitlines() if _ATOM_RE.match(ln))
        if atoms < 3:
            return 0.0
        low = head.lower()
        # Gaussian (.gjf/.com) are practically always inputs; .inp needs a computational marker
        marker = candidate.ext in (".gjf", ".com") or any(
            m in low for m in ("* xyz", "%pal", "%mem", "%chk", "nprocs", "\n!", "\n#", "%method"))
        return 0.75 if marker else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        atoms = _largest_atom_block(candidate.as_text().splitlines())
        if not atoms:
            raise ValueError(
                f"{candidate.filename}: no Cartesian geometry found (Z-matrix / xyzfile not supported)")
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=Metadata(sample_name=candidate.stem),
            structure=Structure3D(data=_to_xyz(atoms, candidate.stem), fmt="xyz",
                                  title=candidate.stem, n_atoms=len(atoms)),
        )


def _largest_atom_block(lines: list[str]) -> list[tuple[str, str, str, str]]:
    """The longest contiguous run of Cartesian atom lines (skips route/title/charge/connectivity)."""
    best: list[tuple[str, str, str, str]] = []
    current: list[tuple[str, str, str, str]] = []
    for line in lines:
        m = _ATOM_RE.match(line)
        if m:
            current.append((m.group(1), m.group(2), m.group(3), m.group(4)))
        else:
            if len(current) > len(best):
                best = current
            current = []
    return current if len(current) > len(best) else best


def _to_xyz(atoms: list[tuple[str, str, str, str]], title: str) -> str:
    lines = [str(len(atoms)), title]
    for sym, x, y, z in atoms:
        lines.append(f"{sym:2s} {float(x):14.6f} {float(y):14.6f} {float(z):14.6f}")
    return "\n".join(lines) + "\n"
