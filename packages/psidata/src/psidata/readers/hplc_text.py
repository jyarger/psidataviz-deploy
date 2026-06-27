"""Reader for **HPLC** chromatograms exported as a plain two-column CSV (retention time, detector signal).

The files are headerless ``time, signal`` pairs (e.g. ``…_THCa_PVP_HPLCdata.csv``). Because a bare
two-column CSV is ambiguous, this reader only claims a file when the HPLC context is clear — the source's
``HPLC`` technique hint or ``hplc`` in the filename — so it doesn't grab unrelated CSV traces.
"""

from __future__ import annotations

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate


@register_reader
class HplcTextReader(BaseReader):
    technique = "HPLC"
    name = "hplc_text"
    version = "0.1.0"
    extensions = (".csv", ".txt")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        has_context = (candidate.technique_hint or "").upper().startswith("HPLC") \
            or "hplc" in candidate.stem.lower()
        if not has_context:
            return 0.0
        return 0.75 if _looks_like_xy(candidate.head(400)) else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        rows = []
        for ln in candidate.as_text().splitlines():
            parts = ln.replace(";", ",").split(",")
            if len(parts) < 2:
                continue
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
        if not rows:
            raise ValueError(f"{candidate.filename}: no numeric (time, signal) rows found")
        frame = pd.DataFrame(rows, columns=["Retention time", "Signal"])
        signal = Signal(
            name="chromatogram",
            x=Axis(label="Retention time", unit="min", quantity="time"),
            y=Axis(label="Signal", unit="a.u.", quantity="intensity"),
            frame=frame,
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=Metadata(sample_name=candidate.stem),
            signals=[signal],
        )


def _looks_like_xy(head: str) -> bool:
    n = 0
    for ln in head.splitlines():
        parts = ln.replace(";", ",").split(",")
        if len(parts) < 2:
            return False
        try:
            float(parts[0])
            float(parts[1])
        except ValueError:
            return False
        n += 1
        if n >= 3:
            return True
    return n >= 1
