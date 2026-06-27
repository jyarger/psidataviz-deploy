"""Reader for **FTIR / IR** spectra in JCAMP-DX (``.jdx`` / ``.dx``).

Shares JCAMP parsing with the NMR reader (:mod:`._jcamp`) but claims ``##DATATYPE= INFRARED
SPECTRUM`` files (Thermo Nicolet, PerkinElmer, Bruker IR). Wavenumber axis (cm⁻¹), with the y label
taken from ``YUNITS`` (transmittance / absorbance / arbitrary). Handles both plain ``(XY..XY)`` and
ASDF-compressed ``(X++(Y..Y))`` data.
"""

from __future__ import annotations

import pandas as pd

from ..model import Axis, Dataset, Signal, SourceInfo
from ..registry import register_reader
from ._jcamp import decode_data, header_index, parse_ldrs_and_data
from .base import BaseReader, Candidate
from .ftir_text import FTIRMetadata


@register_reader
class FtirJcampReader(BaseReader):
    technique = "FTIR"
    name = "ftir_jcamp"
    version = "0.1.0"
    extensions = (".jdx", ".dx")

    def sniff(self, candidate: Candidate) -> float:
        head = candidate.head(4096).upper()
        if "##JCAMP-DX" not in head:
            return 0.0
        base = 0.1 if candidate.ext in self.extensions else 0.0
        if "INFRARED" in head:
            return min(base + 0.7, 1.0)
        if (candidate.technique_hint or "").upper() == "FTIR":
            return min(base + 0.55, 1.0)
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        lines = candidate.as_text().splitlines()
        ldrs, marker, data_lines = parse_ldrs_and_data(lines)
        x, y = decode_data(ldrs, marker, data_lines)

        yunits = (ldrs.get("YUNITS") or "").upper()
        if "TRANS" in yunits:
            y_label, y_quantity, y_unit = "Transmittance", "transmittance", "%"
        elif "ABSORB" in yunits:
            y_label, y_quantity, y_unit = "Absorbance", "absorbance", "a.u."
        else:
            y_label, y_quantity, y_unit = "Intensity", "intensity", "a.u."

        frame = pd.DataFrame({"Wavenumber": x, y_label: y})
        signal = Signal(
            name="spectrum",
            x=Axis(label="Wavenumber", unit="cm⁻¹", quantity="wavenumber"),
            y=Axis(label=y_label, unit=y_unit, quantity=y_quantity),
            frame=frame,
        )
        metadata = FTIRMetadata(
            sample_name=ldrs.get("TITLE") or candidate.stem,
            instrument=ldrs.get("SPECTROMETER/DATASYSTEM") or ldrs.get("ORIGIN"),
            npoints=len(frame),
            wavenumber_range=(float(min(x)), float(max(x))) if x else None,
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version,
                              raw_header="\n".join(lines[: header_index(lines)])),
            metadata=metadata,
            signals=[signal],
        )
