"""Generic reader for **Excel spreadsheets** (``.xlsx``/``.xls``) that hold a real data table.

Lab spreadsheets are messy — merged headers, summary blocks, several sheets. This reader scans every
sheet for the largest *contiguous* numeric block that has a monotonic column to use as **x** plus other
numeric columns as **y** signals, reading the quantity name + unit from the header rows above it. If a
workbook is only a categorical summary (no numeric x/y table), it is declined rather than mis-plotted.

It is a **generic** reader (``technique = "*"``): it applies in any technique folder as a fallback, and
takes the dataset's technique from the folder hint (so a Mechanical ``.xls`` is labelled Mechanical).
"""

from __future__ import annotations

import io
import warnings

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate

_MAX_SIGNALS = 16


@register_reader
class SpreadsheetReader(BaseReader):
    technique = "*"  # generic: matches any folder as a fallback; real technique comes from the hint
    name = "spreadsheet_table"
    version = "0.1.0"
    extensions = (".xlsx", ".xls")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        try:
            return 0.45 if self._choose(candidate) else 0.0
        except Exception:
            return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        chosen = self._choose(candidate)
        if not chosen:
            raise ValueError(f"{candidate.filename}: no numeric x/y table found in any sheet")
        sheet, raw, block = chosen
        xcol = block["xcol"]
        x_label, x_unit = _label(raw, block["r0"], xcol)
        rows = raw.iloc[block["r0"]:block["r1"]]
        xvals = pd.to_numeric(rows[xcol], errors="coerce")
        signals: list[Signal] = []
        for c in block["ycols"][:_MAX_SIGNALS]:
            y_label, y_unit = _label(raw, block["r0"], c)
            yv = pd.to_numeric(rows[c], errors="coerce")
            frame = pd.DataFrame({x_label: xvals.to_numpy(), y_label: yv.to_numpy()}).dropna()
            if frame.empty:
                continue
            signals.append(Signal(
                name=y_label, segment=y_label,
                x=Axis(label=x_label, unit=x_unit, quantity=None),
                y=Axis(label=y_label, unit=y_unit, quantity=None),
                frame=frame,
            ))
        if not signals:
            raise ValueError(f"{candidate.filename}: no usable y columns")
        return Dataset(
            technique=candidate.technique_hint or "Spreadsheet",
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=Metadata(sample_name=candidate.stem,
                              notes=f"sheet '{sheet}'" if sheet else None),
            signals=signals,
        )

    def _choose(self, candidate: Candidate):
        """Return (sheet_name, raw_df, block) for the highest-scoring sheet, or None."""
        engine = "xlrd" if candidate.ext == ".xls" else "openpyxl"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            xls = pd.ExcelFile(io.BytesIO(candidate.content or b""), engine=engine)
            best = None
            for sheet in xls.sheet_names:
                raw = xls.parse(sheet, header=None)
                block = _best_block(raw)
                if block and (best is None or block["score"] > best[2]["score"]):
                    best = (sheet, raw, block)
        return best


def _best_block(raw: pd.DataFrame) -> dict | None:
    """Largest contiguous run of numeric-rich rows that has a monotonic x and >=1 dense y column."""
    num = raw.apply(pd.to_numeric, errors="coerce")
    rich = (num.notna().sum(axis=1) >= 2).to_numpy()
    best = None
    i, n = 0, len(rich)
    while i < n:
        if not rich[i]:
            i += 1
            continue
        j = i
        while j < n and rich[j]:
            j += 1
        if j - i >= 10:
            sub = num.iloc[i:j]
            xcol = next((c for c in sub.columns
                         if sub[c].notna().all()
                         and (sub[c].is_monotonic_increasing or sub[c].is_monotonic_decreasing)), None)
            if xcol is not None:
                thr = max(10, int(0.7 * (j - i)))
                ycols = [c for c in sub.columns if c != xcol and sub[c].notna().sum() >= thr]
                score = (j - i) * len(ycols)
                if ycols and (best is None or score > best["score"]):
                    best = {"r0": i, "r1": j, "xcol": xcol, "ycols": ycols, "score": score}
        i = j
    return best


def _label(raw: pd.DataFrame, r0: int, col) -> tuple[str, str | None]:
    """Read a column's (name, unit) from the one or two header rows above the data block."""
    name = unit = None
    if r0 - 2 >= 0:
        v = raw.iat[r0 - 2, raw.columns.get_loc(col)]
        name = v.strip() if isinstance(v, str) and v.strip() else None
    if r0 - 1 >= 0:
        v = raw.iat[r0 - 1, raw.columns.get_loc(col)]
        h = v.strip() if isinstance(v, str) and v.strip() else None
        if name and h:
            unit = h
        elif h:
            name = h
    return name or f"Column {raw.columns.get_loc(col) + 1}", unit
