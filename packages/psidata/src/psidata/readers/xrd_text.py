"""Reader for **XRD** (X-ray diffraction) patterns in text form.

Handles the common 1D ASCII exports:

* bare ``2θ  intensity`` tables (``.xy``, ``.dat``, ``.asc``), and
* PANalytical ``.csv`` with a ``[Measurement conditions]`` header block and a ``[Scan points]`` table
  (``Angle, TimePerStep, Intensity, ESD``) — the wavelength, sample id, and scan range are pulled into
  metadata.

2D area-detector images (``.tif``/``.edf``/``.img``/``.mccd``/``.h5``) are a separate, large-data concern
and are not handled here. Like Raman, bare ``.xy`` tables are content-ambiguous, so detection leans on the
source folder hinting "XRD".
"""

from __future__ import annotations

import re

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from ._tabular import parse_numeric_table
from .base import BaseReader, Candidate

_XRD_HINTS = {"XRD", "PXRD", "X-RAY", "XRAY", "DIFFRACTION"}
_XRD_CUES = ("measurement conditions", "[scan points]", "scan axis", "k-alpha", "kalpha",
             "2theta", "2-theta", "diffract")


class XRDMetadata(Metadata):
    """XRD-specific metadata layered on the common fields."""

    wavelength_angstrom: float | None = None
    anode: str | None = None
    two_theta_start: float | None = None
    two_theta_end: float | None = None
    npoints: int | None = None


@register_reader
class XRDTextReader(BaseReader):
    technique = "XRD"
    name = "xrd_text"
    version = "0.1.0"
    extensions = (".xy", ".csv", ".dat", ".asc", ".txt")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        low = candidate.head(4096).lower()
        score = 0.6 if (candidate.technique_hint or "").upper() in _XRD_HINTS else 0.0
        if any(cue in low for cue in _XRD_CUES):
            score += 0.5
        if score == 0.0:
            return 0.0
        return min(score, 1.0) if not parse_numeric_table(candidate.head(8192)).empty else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        text = candidate.as_text()
        table = parse_numeric_table(text)
        if table.empty or table.shape[1] < 2:
            raise ValueError(f"No XRD pattern (2θ, intensity) found in {candidate.filename!r}")
        icol = _intensity_column(text, table.shape[1])
        two_theta = table["col0"].rename("2θ")
        intensity = table[f"col{icol}"].rename("Intensity")
        frame = pd.concat([two_theta, intensity], axis=1)
        signal = Signal(
            name="pattern",
            x=Axis(label="2θ", unit="°", quantity="two_theta"),
            y=Axis(label="Intensity", unit="counts", quantity="intensity"),
            frame=frame,
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=_xrd_metadata(text, candidate, two_theta),
            signals=[signal],
        )


def _intensity_column(text: str, ncols: int) -> int:
    """Find the intensity column index from a column-name header line; default to col 1."""
    if ncols == 2:
        return 1
    for line in text.splitlines():
        low = line.lower()
        if "intensity" in low or "counts" in low:
            tokens = [t.strip().lower() for t in re.split(r"[,\t]", line)]
            for i, tok in enumerate(tokens):
                if i < ncols and ("intensity" in tok or "counts" in tok):
                    return i
    return 1


def _header_kv(text: str) -> dict[str, str]:
    """Parse ``key,value`` header lines (PANalytical [Measurement conditions]) into a dict."""
    kv: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("[") or "," not in line:
            continue
        key, _, value = line.partition(",")
        key, value = key.strip(), value.strip().strip('"')
        # stop once we hit numeric data rows (key is a number)
        try:
            float(key)
            break
        except ValueError:
            if key and value:
                kv.setdefault(key, value)
    return kv


def _xrd_metadata(text: str, candidate: Candidate, two_theta: pd.Series) -> XRDMetadata:
    kv = _header_kv(text)
    scan = kv.get("Scan range", "")
    start = end = None
    m = re.findall(r"[-+]?\d*\.?\d+", scan)
    if len(m) >= 2:
        start, end = float(m[0]), float(m[1])
    wl = kv.get("K-Alpha1 wavelength") or kv.get("Wavelength")
    return XRDMetadata(
        sample_name=kv.get("Sample identification") or candidate.stem,
        instrument=kv.get("Anode material") and f"{kv['Anode material']} anode" or None,
        wavelength_angstrom=float(wl) if wl and _is_float(wl) else None,
        anode=kv.get("Anode material"),
        two_theta_start=start if start is not None else float(two_theta.iloc[0]),
        two_theta_end=end if end is not None else float(two_theta.iloc[-1]),
        npoints=len(two_theta),
    )


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False
