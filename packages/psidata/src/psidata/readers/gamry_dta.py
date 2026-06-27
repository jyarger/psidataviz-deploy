"""Reader for **Gamry** electrochemistry ``.DTA`` files (cyclic voltammetry, etc.).

ASCII format: an ``EXPLAIN`` header of ``KEY<TAB>TYPE<TAB>value…`` lines (``TAG`` gives the experiment,
e.g. ``CV``; ``PSTAT``/``DATE``/``SCANRATE`` etc.), then one or more ``CURVEn  TABLE`` blocks — a column
row (``Pt T Vf Im Vu Sig …``), a units row, and tab-delimited data. Potential is **Vf** (V vs. reference)
and current is **Im** (A); each curve becomes one segment. Numbers use a **comma decimal separator**.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate


@register_reader
class GamryDtaReader(BaseReader):
    technique = "Electrochem"
    name = "gamry_dta"
    version = "0.1.0"
    extensions = (".dta",)

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext != ".dta":
            return 0.0
        head = candidate.head(200)
        return 0.9 if head.startswith("EXPLAIN") or "\nTAG\t" in head or head.startswith("TAG\t") else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        text = (candidate.content or b"").decode("latin1", "replace") if candidate.content \
            else candidate.as_text()
        lines = text.splitlines()
        header = _parse_header(lines)
        signals = _parse_curves(lines)
        if not signals:
            raise ValueError(f"{candidate.filename}: no CURVE data table found")
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version, raw_header="\n".join(lines[:60])),
            metadata=Metadata(
                sample_name=candidate.stem,
                instrument=header.get("PSTAT") or "Gamry",
                date=_parse_date(header.get("DATE")),
                operator=header.get("OPERATOR"),
            ),
            signals=signals,
        )


def _parse_header(lines: list[str]) -> dict[str, str]:
    header: dict[str, str] = {}
    for line in lines:
        if line.startswith("CURVE"):
            break
        if "\t" not in line:
            continue
        parts = line.split("\t")
        key = parts[0].strip()
        if key:  # value is the 3rd field (KEY<TAB>TYPE<TAB>value), or the 2nd for 2-field rows like TAG
            header[key] = (parts[2] if len(parts) > 2 else parts[1]).strip()
    return header


def _parse_curves(lines: list[str]) -> list[Signal]:
    signals: list[Signal] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("CURVE"):
            i += 1
            continue
        cols = [c.strip() for c in lines[i + 1].split("\t")]
        try:
            vi, ii = cols.index("Vf"), cols.index("Im")
        except ValueError:
            i += 1
            continue
        rows: list[tuple[float, float]] = []
        j = i + 3  # skip the column row and the units row
        while j < len(lines) and not lines[j].startswith("CURVE") and lines[j].strip():
            parts = lines[j].replace(",", ".").split("\t")  # commas are decimal separators
            if len(parts) > max(vi, ii):
                try:
                    rows.append((float(parts[vi]), float(parts[ii])))
                except ValueError:
                    break  # left the numeric table
            j += 1
        if rows:
            label = lines[i].split("\t")[0].strip() or f"Curve {len(signals) + 1}"
            signals.append(Signal(
                name=label, segment=label,
                x=Axis(label="Potential", unit="V", quantity="potential"),
                y=Axis(label="Current", unit="A", quantity="current"),
                frame=pd.DataFrame(rows, columns=["Potential", "Current"]),
            ))
        i = j
    return signals


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%m.%d.%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None
