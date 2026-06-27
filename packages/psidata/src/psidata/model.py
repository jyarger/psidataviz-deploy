"""Universal data model returned by every reader, for every technique.

The whole extensibility story rests on this: a DSC run, an FTIR spectrum, and an NMR spectrum
all come back as the same ``Dataset`` container, so the app and exporters never need to know
which technique produced the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class Axis(BaseModel):
    """A self-describing plot axis: a human label, a unit, and a canonical quantity name."""

    label: str
    unit: str | None = None
    quantity: str | None = None  # canonical, e.g. "temperature", "heat_flow", "wavenumber"
    scale: str | None = None  # display hint: "log" for axes best shown logarithmically (e.g. frequency)

    model_config = ConfigDict(frozen=True)

    @property
    def title(self) -> str:
        return f"{self.label} ({self.unit})" if self.unit else self.label


class SourceInfo(BaseModel):
    """Provenance for a parsed dataset — where it came from and what parsed it."""

    uri: str | None = None
    filename: str | None = None
    reader: str | None = None
    reader_version: str | None = None
    raw_header: str | None = None


class Metadata(BaseModel):
    """Common metadata shared across techniques. Technique-specific subclasses add fields."""

    model_config = ConfigDict(extra="allow")

    sample_name: str | None = None
    date: _date | None = None
    operator: str | None = None
    instrument: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


@dataclass
class Signal:
    """One curve/trace: an x axis, a y axis, and the underlying tabular data.

    ``frame`` may carry additional columns (e.g. Time) beyond x and y; ``x.label`` and ``y.label``
    name the columns to plot by default.
    """

    name: str
    x: Axis
    y: Axis
    frame: pd.DataFrame
    segment: str | None = None

    def __post_init__(self) -> None:
        for axis in (self.x, self.y):
            if axis.label not in self.frame.columns:
                raise ValueError(
                    f"axis column {axis.label!r} not found in frame columns {list(self.frame.columns)}"
                )

    @property
    def npoints(self) -> int:
        return len(self.frame)


@dataclass
class Image2D:
    """A 2D detector image / map: an intensity array over two axes (e.g. an area-detector frame).

    Used for techniques that produce 2D data (XRD/SAXS/WAXS area detectors, microscopy) rather than a
    1D trace. ``data`` is shape ``(rows, cols)``; ``y`` describes the rows and ``x`` the columns.
    """

    name: str
    data: np.ndarray
    x: Axis
    y: Axis
    z: Axis  # the intensity (colour) axis
    # "map" = a scientific intensity array (shown as a false-colour heatmap); "photo" = a real
    # micrograph/image (grayscale or RGB) shown as-is; "matrix" = a grid the UI slices interactively
    # (e.g. an HPLC-DAD time x wavelength matrix sliced by a wavelength slider).
    kind: str = "map"
    # actual coordinate values for the columns (x) and rows (y); needed when the grid is not a plain
    # pixel index (e.g. real wavelengths / retention times for a "matrix").
    x_values: np.ndarray | None = None
    y_values: np.ndarray | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self.data.shape[0]), int(self.data.shape[1]))


@dataclass
class VibMode:
    """One vibrational normal mode: frequency (cm⁻¹), per-atom displacement vectors, and IR/Raman strength.

    The displacement vectors animate the mode in the 3D viewer (each atom oscillates along its vector).
    """

    freq: float
    disps: list[tuple[float, float, float]]  # one (dx, dy, dz) per atom
    ir: float | None = None
    raman: float | None = None


@dataclass
class Structure3D:
    """A 3D molecular / crystal structure, kept as the **raw structure-file text** plus its format.

    Rendering is done client-side by 3Dmol.js, which has parsers for these formats — so we transport the
    original text verbatim rather than re-encoding atoms. ``fmt`` is a 3Dmol format string
    (``xyz``/``mol``/``sdf``/``pdb``/``mol2``/``cif``). ``modes`` carries vibrational normal modes (from a
    frequency calculation) for animation.
    """

    data: str
    fmt: str
    title: str | None = None
    n_atoms: int | None = None
    modes: list[VibMode] = field(default_factory=list)


@dataclass
class Audio:
    """An audio recording (e.g. an acoustic-interferometry ``.wav``) for in-browser playback.

    The waveform and its FFT travel as ordinary :class:`Signal`\\ s on the dataset; this carries the
    playback parameters and signals that the dataset is playable.
    """

    sample_rate: int
    n_samples: int
    channels: int = 1

    @property
    def duration(self) -> float:
        return self.n_samples / self.sample_rate if self.sample_rate else 0.0


@dataclass
class Dataset:
    """A fully parsed measurement: metadata + 1D signals, 2D images, a 3D structure, and/or audio."""

    technique: str
    source: SourceInfo
    metadata: Metadata
    signals: list[Signal] = field(default_factory=list)
    images: list[Image2D] = field(default_factory=list)
    structure: Structure3D | None = None
    audio: Audio | None = None

    def to_tidy_df(self) -> pd.DataFrame:
        """Long-form concatenation of every signal, tagged with signal/segment columns."""
        frames = []
        for sig in self.signals:
            f = sig.frame.copy()
            f.insert(0, "signal", sig.name)
            f.insert(1, "segment", sig.segment)
            frames.append(f)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def summary(self) -> dict[str, Any]:
        """A cheap, JSON-friendly overview for catalog listings and UI panels."""
        return {
            "technique": self.technique,
            "sample_name": self.metadata.sample_name,
            "date": self.metadata.date.isoformat() if self.metadata.date else None,
            "instrument": self.metadata.instrument,
            "operator": self.metadata.operator,
            "filename": self.source.filename,
            "n_signals": len(self.signals),
            "signals": [
                {
                    "name": s.name,
                    "segment": s.segment,
                    "x": s.x.title,
                    "y": s.y.title,
                    "npoints": s.npoints,
                }
                for s in self.signals
            ],
            "n_images": len(self.images),
            "images": [
                {"name": im.name, "shape": list(im.shape), "x": im.x.title, "y": im.y.title,
                 "z": im.z.title}
                for im in self.images
            ],
            "structure": (
                {"format": self.structure.fmt, "n_atoms": self.structure.n_atoms}
                if self.structure else None
            ),
        }
