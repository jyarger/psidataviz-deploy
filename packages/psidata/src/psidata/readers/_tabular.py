"""Shared helper for headerless / lightly-headed numeric spectral tables.

Used by the FTIR/Raman/NMR/XRD/UV-Vis text readers. It tries the common delimiters (comma, tab,
whitespace), skips header/comment/non-numeric lines, and returns the numeric rows as a DataFrame with
positional column names ``col0, col1, ...``. Picking the delimiter that yields the most consistent
numeric rows makes it robust to header blocks whose first line lacks the data delimiter (e.g. a
PANalytical XRD ``.csv`` starting with ``[Measurement conditions]``).
"""

from __future__ import annotations

import pandas as pd


def detect_delimiter(lines: list[str]) -> str | None:
    """Return ``"\\t"``, ``","``, or ``None`` (whitespace) based on the first data-bearing line."""
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if "\t" in s:
            return "\t"
        if "," in s:
            return ","
        return None  # whitespace-separated
    return None


def _rows_with(lines: list[str], delimiter: str | None) -> tuple[list[list[float]], int | None]:
    rows: list[list[float]] = []
    ncols: int | None = None
    for line in lines:
        s = line.strip()
        if not s:
            continue
        parts = [p for p in (s.split(delimiter) if delimiter else s.split()) if p != ""]
        try:
            values = [float(p) for p in parts]
        except ValueError:
            continue  # header, comment, or non-numeric line
        if ncols is None:
            ncols = len(values)
        if len(values) == ncols and ncols >= 2:
            rows.append(values)
    return rows, ncols


def parse_numeric_table(text: str) -> pd.DataFrame:
    """Parse a numeric table, ignoring header/comment lines and ragged rows.

    The delimiter is chosen as whichever of comma / tab / whitespace yields the most numeric rows, so
    a leading non-delimited header line can't fool the detection.
    """
    lines = text.splitlines()
    best_rows: list[list[float]] = []
    best_ncols: int | None = None
    for delimiter in (",", "\t", None):
        rows, ncols = _rows_with(lines, delimiter)
        if len(rows) > len(best_rows):
            best_rows, best_ncols = rows, ncols
    if not best_rows or best_ncols is None:
        return pd.DataFrame()
    return pd.DataFrame(best_rows, columns=[f"col{i}" for i in range(best_ncols)])
