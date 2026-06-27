"""Reader for TA Instruments Trios DSC text exports (``.txt`` TAB-delimited or ``.csv`` comma-delimited).

Both variants share the exact same structure (only the delimiter differs); the delimiter is
auto-detected. Format (validated against real files in ``github.com/yargerlab/Data/DSC``):

* A header region of ``key<TAB>value`` lines, organized into ``[Section]`` blocks
  (``[Procedure]``, ``[Signal List]``, ``[Method Log]``, ``[Configuration]``, ...).
* One or more data segments, each introduced by a ``[step]`` marker, followed by:
    1. a segment title line (e.g. ``Ramp 10.00 °C/min to 180.00 °C``)
    2. a tab-delimited column-name row (e.g. ``Time<TAB>Temperature<TAB>Heat Flow (Normalized)``)
    3. a tab-delimited units row (e.g. ``min<TAB>°C<TAB>W/g``)
    4. tab-delimited numeric data rows (trailing empty fields possible)

The exported columns come from the per-step header row, NOT from ``[Signal List]`` (which lists
every *available* signal, only a subset of which is exported).
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate

STEP_MARKER = "[step]"

#: Content signatures used for confidence-scored detection.
_SIGNATURES = ("[Signal List]", "proceduresegments", "[Method Log]", STEP_MARKER, "Trios")

# Canonical quantity names keyed by a lowercase substring of the exported column name.
_QUANTITY_BY_COLUMN = {
    "temperature": "temperature",
    "heat flow": "heat_flow",
    "heat capacity": "heat_capacity",
    "time": "time",
}


class DSCMetadata(Metadata):
    """DSC-specific metadata layered on top of the common fields."""

    sample_mass_mg: float | None = None
    pan_type: str | None = None
    exotherm_direction: str | None = None
    trios_version: str | None = None
    procedure_segments: str | None = None
    method_log: list[str] = []
    available_signals: list[str] = []
    n_segments: int = 0


@register_reader
class DscTriosReader(BaseReader):
    technique = "DSC"
    name = "dsc_trios"
    version = "0.1.0"
    extensions = (".txt", ".csv", ".tsv")

    def sniff(self, candidate: Candidate) -> float:
        head = candidate.head(8192)
        score = 0.0
        if candidate.ext in (".txt", ".csv", ".tsv"):
            score += 0.1
        hits = sum(sig in head for sig in _SIGNATURES)
        score += min(hits * 0.25, 0.9)
        return min(score, 1.0)

    def read(self, candidate: Candidate) -> Dataset:
        lines = candidate.as_text().splitlines()
        step_indices = [i for i, line in enumerate(lines) if line.strip() == STEP_MARKER]

        header_lines = lines[: step_indices[0]] if step_indices else lines
        delimiter = _detect_delimiter(header_lines)
        sections = _parse_header(header_lines, delimiter)
        metadata = _build_metadata(sections, n_segments=len(step_indices))

        signals = _parse_segments(lines, step_indices, delimiter)
        metadata.n_segments = len(signals)

        return Dataset(
            technique=self.technique,
            source=SourceInfo(
                uri=candidate.uri,
                filename=candidate.filename,
                reader=self.name,
                reader_version=self.version,
                raw_header="\n".join(header_lines),
            ),
            metadata=metadata,
            signals=signals,
        )


def _detect_delimiter(header_lines: list[str]) -> str:
    """Trios exports are TAB-delimited (.txt) or comma-delimited (.csv); same structure otherwise.

    The header never contains tabs in the comma variant, so a single tab anywhere in the header
    region unambiguously means the tab variant.
    """
    return "\t" if any("\t" in line for line in header_lines) else ","


def _parse_header(header_lines: list[str], delimiter: str) -> dict[str, dict[str, str]]:
    """Group ``key<DELIM>value`` lines into ``{section: {key: value}}`` (top-level under ``_top``).

    Splits on the first delimiter only, so values containing the delimiter (e.g. comments) survive.
    """
    sections: dict[str, dict[str, str]] = {"_top": {}}
    current = "_top"
    for line in header_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
            sections.setdefault(current, {})
            continue
        if delimiter in line:
            key, _, value = line.partition(delimiter)
            sections[current][key.strip()] = value.strip()
    return sections


def _build_metadata(sections: dict[str, dict[str, str]], n_segments: int) -> DSCMetadata:
    top = sections.get("_top", {})
    procedure = sections.get("Procedure", {})
    config = sections.get("Configuration", {})
    fileparams = sections.get("File Parameters", {})

    return DSCMetadata(
        sample_name=top.get("Sample name") or procedure.get("Sample Name"),
        date=_parse_rundate(top.get("rundate") or fileparams.get("Run date")),
        operator=top.get("Operator") or procedure.get("Operator"),
        instrument=config.get("Instrument Type") or config.get("Instrument Name")
        or _strip_paren(top.get("Instrument name")),
        sample_mass_mg=_parse_mass(procedure.get("Sample Mass")),
        pan_type=procedure.get("Pan Type"),
        exotherm_direction=config.get("Exotherm Direction"),
        trios_version=fileparams.get("Trios version"),
        procedure_segments=top.get("proceduresegments"),
        method_log=list(sections.get("Method Log", {}).values()),
        available_signals=list(sections.get("Signal List", {}).values()),
        n_segments=n_segments,
    )


def _parse_segments(lines: list[str], step_indices: list[int], delimiter: str) -> list[Signal]:
    signals: list[Signal] = []
    bounds = step_indices + [len(lines)]
    for idx, start in enumerate(step_indices):
        end = bounds[idx + 1]
        block = lines[start + 1 : end]
        if len(block) < 4:
            continue
        title = block[0].strip()
        columns = [c.strip() for c in block[1].split(delimiter)]
        units = [u.strip() for u in block[2].split(delimiter)]
        frame = _parse_data_rows(block[3:], columns, delimiter)
        if frame.empty:
            continue
        signal = _build_signal(name=f"Segment {idx + 1}: {title}", segment=title,
                               columns=columns, units=units, frame=frame)
        signals.append(signal)
    return signals


def _parse_data_rows(rows: list[str], columns: list[str], delimiter: str) -> pd.DataFrame:
    ncols = len(columns)
    parsed: list[list[float]] = []
    for row in rows:
        parts = row.split(delimiter)
        if len(parts) < ncols:
            continue
        try:
            parsed.append([float(p) for p in parts[:ncols]])
        except ValueError:
            continue  # header/units/blank/partial rows
    return pd.DataFrame(parsed, columns=columns)


def _build_signal(name: str, segment: str, columns: list[str], units: list[str],
                  frame: pd.DataFrame) -> Signal:
    unit_by_col = dict(zip(columns, units, strict=False))
    x_col = _find_column(columns, "temperature") or columns[0]
    y_col = _find_column(columns, "heat flow") or columns[-1]
    return Signal(
        name=name,
        segment=segment,
        x=_axis(x_col, unit_by_col.get(x_col)),
        y=_axis(y_col, unit_by_col.get(y_col)),
        frame=frame,
    )


def _axis(column: str, unit: str | None) -> Axis:
    quantity = next((q for key, q in _QUANTITY_BY_COLUMN.items() if key in column.lower()), None)
    return Axis(label=column, unit=unit or None, quantity=quantity)


def _find_column(columns: list[str], needle: str) -> str | None:
    return next((c for c in columns if needle in c.lower()), None)


def _parse_rundate(value: str | None) -> date | None:
    if not value:
        return None
    token = value.strip().split(" ")[0]  # drop time-of-day if present
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def _parse_mass(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.split()[0])
    except (ValueError, IndexError):
        return None


def _strip_paren(value: str | None) -> str | None:
    if not value:
        return None
    return value.split("(")[0].strip()
