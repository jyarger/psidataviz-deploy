"""Reader for Raman spectra in text tables (``.csv``/``.txt``).

Validated against ``github.com/yargerlab/Data/Raman``: headerless tables of
``shift, intensity[, intensity2, ...]`` — extra intensity columns are repeat accumulations and
become separate signals. Raman ``.csv`` is content-indistinguishable from a generic table, so it's
accepted only when the source folder hints "Raman" (the tiny ``*_spec.txt`` metadata sidecars carry
no numeric table and are ignored).
"""

from __future__ import annotations

import re
from typing import Any

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from ._tabular import parse_numeric_table
from .base import BaseReader, Candidate


class RamanMetadata(Metadata):
    npoints: int | None = None
    n_traces: int = 0


def parse_spec_sidecar(text: str) -> dict[str, Any]:
    """Parse a homebuilt-rig ``*_spec.txt`` companion (laser / power / spectrometer / polarization).

    The LabVIEW Raman exports a free-form sidecar such as::

        Green
        12.0mW
        Andor750 (3)
        Polarized

    Parsed by content (order-tolerant) into laser, laser_power_mw, spectrometer, polarization.
    """
    out: dict[str, Any] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        m = re.fullmatch(r"([\d.]+)\s*mw", low)
        if m:
            out["laser_power_mw"] = float(m.group(1))
        elif low in {"green", "red", "blue", "ir", "nir", "uv", "violet"} or re.search(r"\d{3,4}\s*nm", low):
            out["laser"] = s
        elif "polar" in low:
            out["polarization"] = s
        else:
            out.setdefault("spectrometer", s)
    return out


@register_reader
class RamanTextReader(BaseReader):
    technique = "Raman"
    name = "raman_text"
    version = "0.1.0"
    extensions = (".csv", ".txt")

    def sniff(self, candidate: Candidate) -> float:
        if (candidate.technique_hint or "").upper() != "RAMAN":
            return 0.0  # ambiguous without the folder hint
        if candidate.ext not in self.extensions:
            return 0.0
        return 0.7 if not parse_numeric_table(candidate.head(4096)).empty else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        table = parse_numeric_table(candidate.as_text())
        if table.empty or table.shape[1] < 2:
            raise ValueError(f"No Raman spectrum (shift, intensity) found in {candidate.filename!r}")
        shift = table["col0"].rename("Raman shift")
        intensity_cols = list(table.columns[1:])
        signals = []
        for idx, col in enumerate(intensity_cols, start=1):
            y = table[col].rename("Intensity")
            label = "spectrum" if len(intensity_cols) == 1 else f"accumulation {idx}"
            signals.append(
                Signal(
                    name=label,
                    segment=None if len(intensity_cols) == 1 else label,
                    x=Axis(label="Raman shift", unit="cm⁻¹", quantity="raman_shift"),
                    y=Axis(label="Intensity", unit="a.u.", quantity="intensity"),
                    frame=shift.to_frame().join(y),
                )
            )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=RamanMetadata(sample_name=candidate.stem, npoints=len(shift),
                                   n_traces=len(intensity_cols)),
            signals=signals,
        )
