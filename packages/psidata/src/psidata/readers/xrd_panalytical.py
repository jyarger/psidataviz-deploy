"""Reader for **XRD** patterns in PANalytical / Philips structured 1D formats.

* ``.xrdml`` — PANalytical XML: a ``<counts>``/``<intensities>`` list plus a ``<positions axis="2Theta">``
  start/end, from which the linear 2θ axis is rebuilt.
* ``.udf`` — Philips Universal Data Format (text): a ``Key,Value,/`` header (``DataAngleRange``,
  ``ScanStepSize``, anode, wavelength) followed by a ``RawScan`` block of intensities.

Both carry only intensities + a 2θ start/step (or start/end), so the abscissa is reconstructed rather
than stored per point. Bare ``.xy`` / PANalytical ``.csv`` patterns are handled by ``xrd_text``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from ..model import Axis, Dataset, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate
from .xrd_text import XRDMetadata

_XRD_HINTS = {"XRD", "PXRD", "X-RAY", "XRAY", "DIFFRACTION"}


@register_reader
class XRDPanalyticalReader(BaseReader):
    technique = "XRD"
    name = "xrd_panalytical"
    version = "0.1.0"
    extensions = (".xrdml", ".udf")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        low = candidate.head(2048).lower()
        if candidate.ext == ".xrdml" and "xrdml" in low:
            return 0.95
        if candidate.ext == ".udf" and ("rawscan" in low or "dataanglerange" in low):
            return 0.95
        return 0.6 if (candidate.technique_hint or "").upper() in _XRD_HINTS else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        text = candidate.as_text()
        two_theta, intensity, meta = (
            _read_xrdml(text) if candidate.ext == ".xrdml" else _read_udf(text)
        )
        if len(intensity) == 0:
            raise ValueError(f"No XRD intensities found in {candidate.filename!r}")
        meta.setdefault("sample_name", candidate.stem)
        signal = Signal(
            name="pattern",
            x=Axis(label="2θ", unit="°", quantity="two_theta"),
            y=Axis(label="Intensity", unit="counts", quantity="intensity"),
            frame=pd.DataFrame({"2θ": two_theta, "Intensity": intensity}),
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=XRDMetadata(npoints=len(intensity),
                                 two_theta_start=float(two_theta[0]),
                                 two_theta_end=float(two_theta[-1]), **meta),
            signals=[signal],
        )


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_xrdml(text: str) -> tuple[np.ndarray, np.ndarray, dict]:
    root = ET.fromstring(text.lstrip("﻿"))
    counts_el = next((e for e in root.iter() if _local(e.tag) in ("counts", "intensities")), None)
    intensity = np.array([float(v) for v in (counts_el.text or "").split()]) if counts_el is not None \
        else np.array([])
    start = end = None
    for pos in root.iter():
        if _local(pos.tag) == "positions" and pos.get("axis") == "2Theta":
            children = {_local(c.tag): c.text for c in pos}
            start, end = float(children.get("startPosition", "nan")), float(children.get("endPosition", "nan"))
            break
    n = len(intensity)
    if start is not None and end is not None and n > 1:
        two_theta = np.linspace(start, end, n)
    else:
        two_theta = np.arange(n, dtype=float)
    meta = {k: v for k, v in {
        "sample_name": _first_text(root, "id"),
        "anode": _first_text(root, "anodeMaterial"),
        "wavelength_angstrom": _as_float(_first_text(root, "kAlpha1")),
    }.items() if v is not None}
    return two_theta, intensity, meta


def _first_text(root: ET.Element, name: str) -> str | None:
    el = next((e for e in root.iter() if _local(e.tag) == name and (e.text or "").strip()), None)
    return el.text.strip() if el is not None else None


def _read_udf(text: str) -> tuple[np.ndarray, np.ndarray, dict]:
    lines = text.splitlines()
    kv: dict[str, str] = {}
    data_start = len(lines)
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("rawscan"):
            data_start = i + 1
            break
        if "," in line:
            parts = [p.strip() for p in line.split(",")]
            value = ",".join(p for p in parts[1:] if p not in ("", "/"))
            if parts[0]:
                kv[parts[0]] = value
    intensity = np.array([
        float(tok) for line in lines[data_start:]
        for tok in line.replace(",", " ").split() if _is_float(tok)
    ])
    nums = re.findall(r"[-+]?\d*\.?\d+", kv.get("DataAngleRange", ""))
    start = float(nums[0]) if nums else None
    step = _as_float(kv.get("ScanStepSize"))
    n = len(intensity)
    if start is not None and step:
        two_theta = start + np.arange(n) * step
    elif start is not None and len(nums) >= 2 and n > 1:
        two_theta = np.linspace(start, float(nums[1]), n)
    else:
        two_theta = np.arange(n, dtype=float)
    meta = {k: v for k, v in {
        "sample_name": kv.get("SampleIdent"),
        "anode": kv.get("Anode"),
        "wavelength_angstrom": _as_float(kv.get("LabdaAlpha1")),
    }.items() if v is not None}
    return two_theta, intensity, meta


def _as_float(s: str | None) -> float | None:
    try:
        return float(s) if s not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _is_float(tok: str) -> bool:
    try:
        float(tok)
        return True
    except ValueError:
        return False
