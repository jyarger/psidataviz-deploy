"""Reader for **acoustic interferometry** spectra — the ``Spectrum.csv`` inside an acoustic ``.zip``.

The acoustic-interferometer export bundles the recorded/noise ``.wav`` audio, an ``ExptInfo.txt``, a
``SensorsData.csv`` (temperature/pressure/flow), and a ``Spectrum.csv`` — the FFT of the recorded sound:
two columns, ``Frequency (Hz)`` and ``FFT Magnitude (dB)``. We read that spectrum (the resonance curve);
:func:`psidata.archive.read_zip` picks it out of the bundle by confidence, so the zip "just works".
"""

from __future__ import annotations

import re

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate

_LABEL_RE = re.compile(r"^(?P<label>.*?)\s*(?:\((?P<unit>[^)]*)\))?\s*$")


@register_reader
class AcousticSpectrumReader(BaseReader):
    technique = "Acoustic"
    name = "acoustic_spectrum"
    version = "0.1.0"
    extensions = (".csv",)

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext != ".csv":
            return 0.0
        first = candidate.head(200).splitlines()[:1]
        header = first[0].lower() if first else ""
        # the FFT spectrum header — distinguishes it from the sibling SensorsData.csv
        if "frequency" in header and ("magnitude" in header or "fft" in header or "(db)" in header):
            return 0.92
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        lines = candidate.as_text().splitlines()
        if not lines:
            raise ValueError(f"{candidate.filename}: empty spectrum")
        cols = [c.strip() for c in lines[0].split(",")]
        x_label, x_unit = _split_unit(cols[0] if cols else "Frequency")
        y_label, y_unit = _split_unit(cols[1] if len(cols) > 1 else "FFT Magnitude")

        rows: list[tuple[float, float]] = []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 2:
                continue
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
        if not rows:
            raise ValueError(f"{candidate.filename}: no numeric (frequency, magnitude) rows")

        frame = pd.DataFrame(rows, columns=[x_label, y_label])
        signal = Signal(
            name="spectrum",
            x=Axis(label=x_label, unit=x_unit or "Hz", quantity="frequency"),
            y=Axis(label=y_label, unit=y_unit or "dB", quantity="magnitude"),
            frame=frame,
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=Metadata(sample_name=candidate.stem.replace("_Spectrum", "").rstrip("_- ")),
            signals=[signal],
        )


def _split_unit(label: str) -> tuple[str, str | None]:
    m = _LABEL_RE.match(label.strip())
    if not m:
        return label, None
    return (m.group("label") or label).strip(), (m.group("unit").strip() if m.group("unit") else None)
