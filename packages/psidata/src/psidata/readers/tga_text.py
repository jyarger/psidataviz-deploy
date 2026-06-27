"""Reader for **TA Instruments TGA** text exports (older *Thermal Advantage* / *Universal Analysis* ``.txt``).

Format (TA 2950 TGA ``V5.4A``, validated on real Drive data): a header of TAB-delimited ``Key<TAB>value``
lines (``Instrument``, ``Module``, ``Sample``, ``Size``, ``Method``, ``Operator``, ``Nsig``,
``Sig1``..``SigN``, ``Xcomment`` with the purge-gas info, …), a ``StartOfData`` marker, then TAB-delimited
numeric rows with one column per signal (typically Time, Temperature, Weight). The canonical TGA curve is
**weight %** vs **temperature**, so that is the signal produced (normalized to the first point).
"""

from __future__ import annotations

import re
from datetime import date, datetime

import numpy as np
import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate

DATA_MARKER = "StartOfData"
_SIG_RE = re.compile(r"^(?P<label>.*?)\s*(?:\((?P<unit>[^)]*)\))?\s*$")


class TGAMetadata(Metadata):
    """TGA-specific metadata layered on the common fields."""

    sample_mass_mg: float | None = None
    method: str | None = None
    module: str | None = None
    atmosphere: str | None = None


@register_reader
class TgaTextReader(BaseReader):
    technique = "TGA"
    name = "tga_text"
    version = "0.1.0"
    extensions = (".txt",)

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext != ".txt":
            return 0.0
        low = candidate.head(2000).lower()
        # the StartOfData header + a Weight signal distinguishes a TGA export from the (Heat-Flow) DSC one
        if "startofdata" in low and "weight" in low and ("tga" in low or "\nsig" in low or "nsig" in low):
            return 0.92
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        # TA's older software writes the degree sign as byte 0xF8 (DOS code page 437), so decode as cp437
        raw = candidate.content or b""
        text = raw.decode("cp437", "replace") if raw else candidate.as_text()
        lines = text.splitlines()
        start = next((i for i, ln in enumerate(lines) if ln.strip() == DATA_MARKER), None)
        if start is None:
            raise ValueError(f"{candidate.filename}: TGA export missing '{DATA_MARKER}' marker")

        header = _parse_header(lines[:start])
        labels, units = _columns(header)
        frame = _parse_data(lines[start + 1:], labels)
        if frame.empty:
            raise ValueError(f"{candidate.filename}: TGA export had no numeric data")

        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version, raw_header="\n".join(lines[:start])),
            metadata=_metadata(header, candidate.stem),
            signals=[_tga_signal(frame, labels, units)],
        )


def _parse_header(lines: list[str]) -> dict[str, str]:
    """``Key<TAB>value`` lines into a dict (first value wins; the value keeps any later tabs)."""
    header: dict[str, str] = {}
    for line in lines:
        if "\t" not in line:
            continue
        key, _, value = line.partition("\t")
        header.setdefault(key.strip(), value.strip())
    return header


def _columns(header: dict[str, str]) -> tuple[list[str], list[str | None]]:
    n = int(_float(header.get("Nsig")) or 0)
    labels: list[str] = []
    units: list[str | None] = []
    for i in range(1, n + 1):
        raw = header.get(f"Sig{i}", f"Col{i}").split("\t")[0].strip()
        m = _SIG_RE.match(raw)
        labels.append((m.group("label") or raw).strip() if m else raw)
        units.append((m.group("unit").strip() or None) if (m and m.group("unit")) else None)
    return labels, units


def _parse_data(rows: list[str], labels: list[str]) -> pd.DataFrame:
    n = len(labels)
    parsed: list[list[float]] = []
    for row in rows:
        parts = row.split("\t")
        if len(parts) < n:
            continue
        try:
            parsed.append([float(p) for p in parts[:n]])
        except ValueError:
            continue
    return pd.DataFrame(parsed, columns=labels)


def _tga_signal(frame: pd.DataFrame, labels: list[str], units: list[str | None]) -> Signal:
    unit_by = dict(zip(labels, units, strict=False))
    temp = _find(labels, "temperature") or labels[min(1, len(labels) - 1)]
    weight = _find(labels, "weight") or labels[-1]
    w = frame[weight].to_numpy(dtype=float)
    w0 = w[0] if w.size and w[0] else (np.nanmax(w) if w.size else 1.0)
    out = pd.DataFrame({temp: frame[temp].to_numpy(dtype=float), "Weight": w / w0 * 100.0})
    return Signal(
        name="TGA",
        x=Axis(label=temp, unit=unit_by.get(temp) or "°C", quantity="temperature"),
        y=Axis(label="Weight", unit="%", quantity="mass"),
        frame=out,
    )


def _metadata(header: dict[str, str], stem: str) -> TGAMetadata:
    return TGAMetadata(
        sample_name=header.get("Sample") or stem,
        operator=header.get("Operator"),
        instrument=_clean(header.get("Instrument")),
        date=_parse_date(header.get("Date")),
        sample_mass_mg=_float(header.get("Size")),
        method=header.get("Method"),
        module=_clean(header.get("Module")),
        atmosphere=_clean(header.get("Xcomment")),
    )


def _find(labels: list[str], needle: str) -> str | None:
    return next((c for c in labels if needle in c.lower()), None)


def _clean(value: str | None) -> str | None:
    return " ".join(value.split()) if value and value.strip() else None


def _float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.split()[0])
    except (ValueError, IndexError):
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None
