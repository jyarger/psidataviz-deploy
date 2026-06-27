"""Reader for NMR spectra in plain delimited text (``.tsv``) — chemical shift (ppm) vs intensity.

For TopSpin-style exports with no JCAMP header (e.g. a ``x<TAB>y`` ``.tsv``). The content is an
ambiguous numeric table, so it is claimed only when the source folder hints "NMR"; the nucleus is
recovered from the filename (e.g. ``…_13C`` / ``…_1H``) since these files carry no header metadata.
"""

from __future__ import annotations

import re

from ..model import Axis, Dataset, Signal, SourceInfo
from ..registry import register_reader
from ._tabular import parse_numeric_table
from .base import BaseReader, Candidate
from .nmr_jcamp import NMRMetadata

_NUCLEUS_RE = re.compile(r"(?:^|[_\-])(\d+[A-Z][a-z]?)(?:[_\-]|$)")


@register_reader
class NmrTextReader(BaseReader):
    technique = "NMR"
    name = "nmr_text"
    version = "0.1.0"
    extensions = (".tsv",)

    def sniff(self, candidate: Candidate) -> float:
        if (candidate.technique_hint or "").upper() != "NMR":
            return 0.0  # ambiguous numeric table; needs the folder hint
        if candidate.ext not in self.extensions:
            return 0.0
        return 0.7 if not parse_numeric_table(candidate.head(4096)).empty else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        table = parse_numeric_table(candidate.as_text())
        if table.empty or table.shape[1] < 2:
            raise ValueError(f"No NMR spectrum (shift, intensity) found in {candidate.filename!r}")
        shift = table["col0"].rename("Chemical shift")
        intensity = table["col1"].rename("Intensity")
        signal = Signal(
            name="spectrum",
            x=Axis(label="Chemical shift", unit="ppm", quantity="chemical_shift"),
            y=Axis(label="Intensity", unit="a.u.", quantity="intensity"),
            frame=shift.to_frame().join(intensity),
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=NMRMetadata(sample_name=candidate.stem, npoints=len(shift),
                                 nucleus=_nucleus_from_name(candidate.stem)),
            signals=[signal],
        )


def _nucleus_from_name(stem: str) -> str | None:
    m = _NUCLEUS_RE.search(stem)
    return m.group(1) if m else None
