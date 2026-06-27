"""Reader for FTIR spectra in simple text tables (Bruker ``.dpt``, plus ``.csv``/``.txt``/``.asc``).

Validated against ``github.com/yargerlab/Data/FTIR``: ``.dpt`` files are headerless two-column
tables (wavenumber, absorbance), tab-delimited, descending wavenumber. ``.dpt`` is IR-specific so
it's detected by extension; the ambiguous ``.csv``/``.txt`` variants are accepted when the source
folder hints "FTIR".
"""

from __future__ import annotations

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from ._tabular import parse_numeric_table
from .base import BaseReader, Candidate


class FTIRMetadata(Metadata):
    npoints: int | None = None
    wavenumber_range: tuple[float, float] | None = None


@register_reader
class FtirTextReader(BaseReader):
    technique = "FTIR"
    name = "ftir_text"
    version = "0.1.0"
    extensions = (".dpt", ".csv", ".txt", ".asc")

    def sniff(self, candidate: Candidate) -> float:
        looks_numeric = not parse_numeric_table(candidate.head(4096)).empty
        if not looks_numeric:
            return 0.0
        if candidate.ext == ".dpt":
            return 0.85  # IR-specific extension
        if (candidate.technique_hint or "").upper() == "FTIR" and candidate.ext in self.extensions:
            return 0.7
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        table = parse_numeric_table(candidate.as_text())
        if table.empty:
            raise ValueError(f"No numeric spectrum found in {candidate.filename!r}")
        x = table["col0"].rename("Wavenumber")
        y = table["col1"].rename("Absorbance")
        frame = x.to_frame().join(y)
        signal = Signal(
            name="spectrum",
            x=Axis(label="Wavenumber", unit="cm⁻¹", quantity="wavenumber"),
            y=Axis(label="Absorbance", unit="a.u.", quantity="absorbance"),
            frame=frame,
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=FTIRMetadata(
                sample_name=candidate.stem,
                npoints=len(frame),
                wavenumber_range=(float(x.min()), float(x.max())),
            ),
            signals=[signal],
        )
