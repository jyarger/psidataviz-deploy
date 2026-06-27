"""Reader for **broadband dielectric spectroscopy** ASCII tables.

The data is a CSV whose first column is frequency (``f / Hz``) and whose remaining columns are the
permittivity at a series of temperatures (``T=324.99K``, ``T=319.99K``, …). The filename says whether it
is the real part ε′ (``…-Eps-Real.dat``, the dielectric constant) or the imaginary part ε″
(``…-Eps-Imag.dat``, the loss). Each temperature column becomes one segment, on a frequency axis.
"""

from __future__ import annotations

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate


@register_reader
class DielectricTextReader(BaseReader):
    technique = "Dielectric"
    name = "dielectric_text"
    version = "0.1.0"
    extensions = (".dat", ".txt", ".csv")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        first = candidate.head(200).splitlines()[0].strip().lower() if candidate.head(200) else ""
        # distinctive header: a frequency column followed by temperature columns
        if first.startswith(("f / hz", "f/hz", "freq")) and "t=" in first:
            return 0.9
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        lines = [ln for ln in candidate.as_text().splitlines() if ln.strip()]
        header = [h.strip() for h in lines[0].split(",")]
        rows = []
        for ln in lines[1:]:
            parts = ln.split(",")
            try:
                rows.append([float(p) for p in parts])
            except ValueError:
                continue
        df = pd.DataFrame(rows, columns=header[: len(rows[0])] if rows else header)
        freq_col = df.columns[0]

        part = "ε″ (loss)" if "imag" in candidate.stem.lower() else \
               "ε′" if "real" in candidate.stem.lower() else "ε"
        signals = []
        for col in df.columns[1:]:
            sub = df[[freq_col, col]].dropna()
            signals.append(Signal(
                name=col, segment=col,
                x=Axis(label="Frequency", unit="Hz", quantity="frequency", scale="log"),
                y=Axis(label=part, unit=None, quantity="permittivity"),
                frame=pd.DataFrame({"Frequency": sub[freq_col].to_numpy(),
                                    part: sub[col].to_numpy()}),
            ))
        if not signals:
            raise ValueError(f"{candidate.filename}: no dielectric columns parsed")
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version, raw_header=lines[0]),
            metadata=Metadata(sample_name=candidate.stem),
            signals=signals,
        )
