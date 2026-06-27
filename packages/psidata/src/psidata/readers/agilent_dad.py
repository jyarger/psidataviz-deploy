"""Reader for **Agilent ChemStation DAD** chromatograms (``DAD1.CSV`` inside a ``.D`` run folder).

The file is a UTF-16 matrix: the first row lists detector wavelengths (``210 … 450`` nm), the first column
is retention time (min), and each cell is the absorbance (mAU) at that time and wavelength. We extract
single-wavelength chromatograms at the standard HPLC detection wavelengths present in the data.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

from ..model import Axis, Dataset, Image2D, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate

_MATRIX_MAX_TIME = 600  # downsample the time axis of the full matrix for compact, sliceable transport

_TARGET_WAVELENGTHS = (210, 230, 254, 280, 320)  # common HPLC-DAD detection wavelengths


@register_reader
class AgilentDadReader(BaseReader):
    technique = "HPLC"
    name = "agilent_dad"
    version = "0.1.0"
    extensions = (".csv",)

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext != ".csv":
            return 0.0
        content = candidate.content or b""
        if content[:2] not in (b"\xff\xfe", b"\xfe\xff"):  # DAD exports are UTF-16
            return 0.0
        if "dad" in candidate.stem.lower():
            return 0.9
        # otherwise: first row should be a list of numeric wavelengths after an empty first cell
        try:
            first = content[:400].decode("utf-16", "ignore").splitlines()[0].split(",")
            if len(first) > 4 and all(_is_int(c) for c in first[1:4]):
                return 0.7
        except (IndexError, ValueError):
            pass
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        df = pd.read_csv(io.BytesIO(candidate.content or b""), encoding="utf-16")
        time = pd.to_numeric(df.iloc[:, 0], errors="coerce")
        wl_cols: dict[int, str] = {}
        for col in df.columns[1:]:
            if _is_int(str(col)):
                wl_cols[int(float(col))] = col
        available = sorted(wl_cols)
        if not available:
            raise ValueError(f"{candidate.filename}: no wavelength columns found")

        signals: list[Signal] = []
        used: set[int] = set()
        for target in _TARGET_WAVELENGTHS:
            nearest = min(available, key=lambda w: abs(w - target))
            if abs(nearest - target) > 6 or nearest in used:
                continue
            used.add(nearest)
            absorbance = pd.to_numeric(df[wl_cols[nearest]], errors="coerce")
            frame = pd.DataFrame({"Retention time": time, "Absorbance": absorbance}).dropna()
            signals.append(Signal(
                name=f"{nearest} nm", segment=f"{nearest} nm",
                x=Axis(label="Retention time", unit="min", quantity="time"),
                y=Axis(label="Absorbance", unit="mAU", quantity="absorbance"),
                frame=frame,
            ))
        if not signals:
            raise ValueError(f"{candidate.filename}: no usable chromatograms")
        matrix = _dad_matrix(df, time, wl_cols, available)
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=Metadata(sample_name=_run_name(candidate),
                              notes=f"DAD {available[0]}–{available[-1]} nm"),
            signals=signals,
            images=[matrix],
        )


def _dad_matrix(df: pd.DataFrame, time: pd.Series, wl_cols: dict[int, str],
                wavelengths: list[int]) -> Image2D:
    """The full time x wavelength absorbance matrix (rows = wavelength), for the wavelength-slider view."""
    grid = np.column_stack([pd.to_numeric(df[wl_cols[w]], errors="coerce").to_numpy()
                            for w in wavelengths]).T  # (n_wavelength, n_time)
    times = time.to_numpy()
    step = max(1, len(times) // _MATRIX_MAX_TIME)
    grid = np.nan_to_num(grid[:, ::step])
    return Image2D(
        name="DAD matrix",
        data=grid,
        x=Axis(label="Retention time", unit="min", quantity="time"),
        y=Axis(label="Wavelength", unit="nm", quantity="wavelength"),
        z=Axis(label="Absorbance", unit="mAU", quantity="absorbance"),
        kind="matrix",
        x_values=times[::step],
        y_values=np.asarray(wavelengths, dtype=float),
    )


def _is_int(value: str) -> bool:
    try:
        int(float(value))
        return True
    except (ValueError, TypeError):
        return False


def _run_name(candidate: Candidate) -> str:
    """Use the ``.D`` run-folder name (e.g. ``ba_1``) when the file is the generic ``DAD1.CSV``."""
    for part in (candidate.uri or candidate.filename or "").replace("\\", "/").split("/"):
        if part.lower().endswith(".d"):
            return part[:-2]
    return candidate.stem
