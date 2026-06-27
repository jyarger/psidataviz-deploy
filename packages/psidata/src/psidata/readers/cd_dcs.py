"""Reader for **circular dichroism** spectra in the ``.dcs`` text format.

A ``.dcs`` file has an ``@!`` header (``@!NAME:``, ``@!MIN:``/``@!MAX:`` wavelength range, plus
deconvolution parameters) followed by ``>``-delimited sections of ``wavelength<TAB>value`` rows. The file
typically carries the measured spectrum first and then many replicate sections (a bootstrap error
analysis); we plot the **first** section as the CD spectrum and note how many replicates accompany it.
"""

from __future__ import annotations

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate


@register_reader
class CircularDichroismDcsReader(BaseReader):
    technique = "CD"
    name = "cd_dcs"
    version = "0.1.0"
    extensions = (".dcs",)

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext != ".dcs":
            return 0.0
        return 0.9 if candidate.head(64).lstrip().startswith("@!") else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        lines = candidate.as_text().splitlines()
        header: dict[str, str] = {}
        i = 0
        while i < len(lines) and lines[i].startswith("@!"):
            key, _, value = lines[i][2:].partition(":")
            header[key.strip().upper()] = value.strip()
            i += 1
        n_sections = sum(1 for ln in lines if ln.startswith(">"))
        while i < len(lines) and not lines[i].startswith(">"):
            i += 1
        i += 1  # step past the first ">" marker
        wl: list[float] = []
        cd: list[float] = []
        while i < len(lines) and not lines[i].startswith(">"):
            parts = lines[i].replace("\t", " ").split()
            if len(parts) >= 2:
                try:
                    wl.append(float(parts[0]))
                    cd.append(float(parts[1]))
                except ValueError:
                    pass
            i += 1
        if not wl:
            raise ValueError(f"{candidate.filename}: no CD spectrum rows found")
        signal = Signal(
            name="CD spectrum",
            x=Axis(label="Wavelength", unit="nm", quantity="wavelength"),
            y=Axis(label="CD", unit="mdeg", quantity="ellipticity"),
            frame=pd.DataFrame({"Wavelength": wl, "CD": cd}),
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=Metadata(sample_name=header.get("NAME") or candidate.stem,
                              notes=f"{n_sections} replicate section(s) in file" if n_sections > 1 else None),
            signals=[signal],
        )
