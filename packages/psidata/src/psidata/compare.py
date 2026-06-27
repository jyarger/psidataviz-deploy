"""Compare the same measurement parsed from different file formats.

When a dataset is saved in several formats (e.g. a DSC run as ``.csv`` *and* ``.txt``), this tells
you whether they hold identical data and, if not, summarizes exactly what differs — signal counts,
point counts, numeric values (within tolerance), and metadata fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .model import Dataset

_SKIP_META = {"extra"}


@dataclass
class Comparison:
    identical: bool
    differences: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return "identical data" if self.identical else f"{len(self.differences)} difference(s)"

    def as_dict(self) -> dict:
        return {"identical": self.identical, "summary": self.summary,
                "differences": self.differences}


def compare_datasets(a: Dataset, b: Dataset, *, rtol: float = 1e-5, atol: float = 1e-8,
                     a_label: str = "A", b_label: str = "B") -> Comparison:
    """Compare two parsed datasets; return an itemized list of any differences."""
    diffs: list[str] = []

    if a.technique != b.technique:
        diffs.append(f"technique: {a.technique} vs {b.technique}")
    if len(a.signals) != len(b.signals):
        diffs.append(f"signal count: {len(a.signals)} ({a_label}) vs {len(b.signals)} ({b_label})")

    for i, (sa, sb) in enumerate(zip(a.signals, b.signals, strict=False)):
        if sa.npoints != sb.npoints:
            diffs.append(f"signal {i} '{sa.name}': {sa.npoints} vs {sb.npoints} points")
            continue
        for col in [c for c in sa.frame.columns if c in sb.frame.columns]:
            ca, cb = sa.frame[col], sb.frame[col]
            if pd.api.types.is_numeric_dtype(ca) and pd.api.types.is_numeric_dtype(cb):
                va, vb = ca.to_numpy(), cb.to_numpy()
                if not np.allclose(va, vb, rtol=rtol, atol=atol, equal_nan=True):
                    diffs.append(f"signal {i} column '{col}': max abs diff "
                                 f"{float(np.nanmax(np.abs(va - vb))):.3g}")
            elif not ca.equals(cb):
                diffs.append(f"signal {i} column '{col}': non-numeric values differ")

    ma, mb = a.metadata.model_dump(), b.metadata.model_dump()
    for key in sorted((set(ma) & set(mb)) - _SKIP_META):
        if ma[key] != mb[key]:
            diffs.append(f"metadata '{key}': {ma[key]!r} vs {mb[key]!r}")

    return Comparison(identical=not diffs, differences=diffs)


def compare_record_formats(record, load) -> dict:
    """Parse every parseable format of a :class:`DataRecord` and compare each to the primary.

    ``load(name, url, technique) -> Dataset`` fetches+parses one variant (kept as a callable so the
    library stays framework-agnostic). Returns a JSON-friendly summary of how the ASCII formats of
    the *same* dataset agree or differ — the answer to "are my .csv and .jdx really the same data?".
    """
    variants = record.parseable_variants
    formats = [v.ext for v in variants]
    if len(variants) < 2:
        return {"comparable": False, "reason": "only one parseable format", "formats": formats}

    primary = record.primary
    base = load(primary.file.name, primary.file.download_url, technique=record.technique)

    comparisons: dict[str, dict] = {}
    for variant in variants:
        if variant is primary:
            continue
        try:
            other = load(variant.file.name, variant.file.download_url, technique=record.technique)
            comparisons[variant.ext] = compare_datasets(
                base, other, a_label=primary.ext, b_label=variant.ext
            ).as_dict()
        except Exception as exc:  # noqa: BLE001 - a bad variant shouldn't sink the whole compare
            comparisons[variant.ext] = {"error": str(exc)}

    n_identical = sum(1 for c in comparisons.values() if c.get("identical"))
    return {
        "comparable": True,
        "technique": record.technique,
        "primary": primary.ext,
        "formats": formats,
        "comparisons": comparisons,
        "summary": f"{primary.ext} vs {len(comparisons)} other ASCII format(s): "
                   f"{n_identical} identical, {len(comparisons) - n_identical} differ",
    }
