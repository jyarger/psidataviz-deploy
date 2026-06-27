"""Reader for **computed IR / Raman spectra** exported from quantum-chemistry calculations.

GaussView-style ``*_ir.txt`` / ``*_raman.txt`` exports (from a Gaussian/ORCA/Psi4 frequency job) carry
a ``# IR Spectrum`` / ``# Raman Activity Spectrum`` header, a ``# Peak information`` stick list, and a
dense broadened spectrum. We read the broadened curve on a wavenumber axis so it can be **overlaid on an
experimental FTIR / Raman spectrum**. The DFT method/basis is recovered from the filename.
"""

from __future__ import annotations

import re

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from ._tabular import parse_numeric_table
from .base import BaseReader, Candidate


class ComputedMetadata(Metadata):
    spectrum_type: str | None = None   # "IR" or "Raman"
    method: str | None = None          # e.g. B3LYP, WB97XD, AM1
    basis_set: str | None = None       # e.g. 6-31+G(d), 6-311++G(2d,3p)
    npoints: int | None = None


@register_reader
class ComputedSpectrumReader(BaseReader):
    technique = "Computational"
    name = "comp_spectrum"
    version = "0.1.0"
    extensions = (".txt",)

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        head = candidate.head(300).lower()
        # the GaussView export headers — specific enough not to grab experimental note files
        if "# ir spectrum" in head or "raman activity spectrum" in head:
            return 0.9
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        text = candidate.as_text()
        is_raman = "raman" in text[:300].lower()
        table = parse_numeric_table(text)  # the broadened spectrum (peak list is #-commented out)
        if table.empty or table.shape[1] < 2:
            raise ValueError(f"No computed spectrum (wavenumber, intensity) in {candidate.filename!r}")
        y_label = "Raman activity" if is_raman else "Intensity"
        wavenumber = table["col0"].rename("Wavenumber")
        intensity = table["col1"].rename(y_label)
        signal = Signal(
            name="computed spectrum",
            x=Axis(label="Wavenumber", unit="cm⁻¹", quantity="wavenumber"),
            y=Axis(label=y_label, unit="a.u.", quantity="intensity"),
            frame=wavenumber.to_frame().join(intensity),
        )
        method, basis = _method_basis(candidate.stem)
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=ComputedMetadata(
                sample_name=candidate.stem, spectrum_type="Raman" if is_raman else "IR",
                method=method, basis_set=basis, npoints=len(wavenumber),
            ),
            signals=[signal],
        )


# common DFT methods / basis-set fragments seen in filenames
_METHODS = ("WB97XD", "B3LYP", "CAM-B3LYP", "PBE0", "PBE", "M06-2X", "M062X", "HF", "MP2", "AM1", "PM3", "PM6")
_BASIS_RE = re.compile(
    r"(6-?311\+?\+?[gG]?[a-zA-Z0-9()+]*|6-?31\+?\+?[gG]?[a-zA-Z0-9()+]*|def2-?[a-zA-Z]+|cc-?pv[a-zA-Z0-9]+|sto-?3g)",
    re.I,
)


def _method_basis(stem: str) -> tuple[str | None, str | None]:
    up = stem.upper().replace("_", " ")
    method = next((m for m in _METHODS if m in up), None)
    m = _BASIS_RE.search(stem)
    return method, (m.group(0) if m else None)
