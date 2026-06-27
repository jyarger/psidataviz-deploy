"""Reader for **PerkinElmer FTIR** ``.asc`` exports (PE IR SUBTECH SPECTRUM ASCII / PEDS).

These have a structured header — a magic line, dates, a sample description, then ``#HDR`` / ``#GR``
(units: e.g. ``cm-1`` / ``%T``) / ``#DATA`` blocks, followed by tab-separated wavenumber, value.
The header's stray single-number lines defeat the generic table reader, so this format needs its
own parser (and the header carries the sample description worth keeping).
"""

from __future__ import annotations

import re

import pandas as pd

from ..model import Axis, Dataset, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate
from .ftir_text import FTIRMetadata


@register_reader
class FtirPerkinElmerAscReader(BaseReader):
    technique = "FTIR"
    name = "ftir_pe_asc"
    version = "0.1.0"
    extensions = (".asc",)

    def sniff(self, candidate: Candidate) -> float:
        head = candidate.head(2048)
        if "PE IR" in head:
            return 0.9
        if candidate.ext == ".asc" and "#DATA" in head:
            return 0.8
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        lines = candidate.as_text().splitlines()
        try:
            data_idx = next(i for i, line in enumerate(lines) if line.strip() == "#DATA")
        except StopIteration as exc:
            raise ValueError(f"No #DATA block in {candidate.filename!r}") from exc
        gr_idx = next((i for i, line in enumerate(lines) if line.strip() == "#GR"), None)

        x_unit, y_label, y_unit, y_quantity = "cm⁻¹", "Transmittance", "%T", "transmittance"
        if gr_idx is not None and gr_idx + 2 < len(lines):
            gx, gy = lines[gr_idx + 1].strip(), lines[gr_idx + 2].strip()
            if gx:
                x_unit = "cm⁻¹" if gx.lower() in ("cm-1", "cm−1", "1/cm") else gx
            if gy:
                if gy.lower().startswith("a"):
                    y_label, y_unit, y_quantity = "Absorbance", "a.u.", "absorbance"
                else:
                    y_label, y_unit = "Transmittance", gy

        xs: list[float] = []
        ys: list[float] = []
        for line in lines[data_idx + 1:]:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.replace(",", " ").split()
            if len(parts) < 2:
                continue
            try:
                xs.append(float(parts[0]))
                ys.append(float(parts[1]))
            except ValueError:
                continue
        if not xs:
            raise ValueError(f"No data rows after #DATA in {candidate.filename!r}")

        frame = pd.DataFrame({"Wavenumber": xs, y_label: ys})
        signal = Signal(
            name="spectrum",
            x=Axis(label="Wavenumber", unit=x_unit, quantity="wavenumber"),
            y=Axis(label=y_label, unit=y_unit, quantity=y_quantity),
            frame=frame,
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version,
                              raw_header="\n".join(lines[: gr_idx if gr_idx else data_idx])),
            metadata=FTIRMetadata(
                sample_name=_description(lines[: gr_idx if gr_idx else data_idx], candidate.stem),
                instrument="PerkinElmer",
                npoints=len(xs),
                wavenumber_range=(float(min(xs)), float(max(xs))),
            ),
            signals=[signal],
        )


def _description(header: list[str], fallback: str) -> str:
    candidates = [
        line.strip() for line in header[1:]
        if re.search("[A-Za-z]", line) and "PE IR" not in line
        and not line.strip().lower().endswith(".asc")
    ]
    for line in candidates:
        if any(word in line for word in ("Sample", "By", "Date")):
            return line
    return candidates[0] if candidates else fallback
