"""Reader for **computational output files** (``.log`` / ``.out``) via **cclib**.

cclib is the de-facto standard parser for Gaussian, ORCA, Q-Chem, NWChem, Psi4, GAMESS, … outputs.
For a frequency job we pull the vibrational frequencies and IR / Raman intensities and broaden the
stick spectrum (Lorentzian) into a continuous curve on a wavenumber axis — so a *computed* IR/Raman
spectrum can be overlaid on an experimental one. The DFT method/basis come from the filename, the
package from cclib's metadata.
"""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pandas as pd

from ..model import Axis, Dataset, Signal, SourceInfo, Structure3D, VibMode
from ..registry import register_reader
from .base import BaseReader, Candidate
from .comp_spectrum import ComputedMetadata, _method_basis

# package banners that identify a computational output (lower-cased)
_PKG_MARKERS = ("entering gaussian system", "gaussian(r)", "o   r   c   a", "q-chem", "nwchem",
                "psi4", "gamess", "molpro", "* o   r   c   a *")


@register_reader
class CompLogReader(BaseReader):
    technique = "Computational"
    name = "comp_log"
    version = "0.1.0"
    extensions = (".log", ".out")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        low = candidate.head(4000).lower()
        return 0.85 if any(m in low for m in _PKG_MARKERS) else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        try:
            import cclib
        except ImportError as exc:
            raise ImportError("reading computational .log/.out needs cclib: "
                              "pip install 'psidata[convert]'") from exc
        fd, tmp = tempfile.mkstemp(suffix=candidate.ext)
        try:
            os.write(fd, candidate.content or candidate.as_text().encode())
            os.close(fd)
            data = cclib.io.ccread(tmp)
        finally:
            os.unlink(tmp)

        freqs = np.asarray(getattr(data, "vibfreqs", None) if data is not None else None, dtype=float) \
            if data is not None and getattr(data, "vibfreqs", None) is not None else None
        if freqs is None or freqs.size == 0:
            raise ValueError(f"no vibrational frequencies in {candidate.filename!r}")

        signals = []
        if getattr(data, "vibirs", None) is not None:
            signals.append(_spectrum("IR", freqs, np.asarray(data.vibirs, float), "IR intensity"))
        if getattr(data, "vibramans", None) is not None:
            signals.append(_spectrum("Raman", freqs, np.asarray(data.vibramans, float), "Raman activity"))
        if not signals:
            raise ValueError(f"no IR or Raman intensities in {candidate.filename!r}")

        method, basis = _method_basis(candidate.stem)
        package = (getattr(data, "metadata", None) or {}).get("package")
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=ComputedMetadata(
                sample_name=candidate.stem, method=method, basis_set=basis, instrument=package,
                spectrum_type=" + ".join(s.segment for s in signals), npoints=int(freqs.size),
            ),
            signals=signals,
            structure=_structure_from_ccdata(data, candidate.stem),
        )


def _structure_from_ccdata(data, title: str) -> Structure3D | None:
    """Build an XYZ structure from cclib's final optimized geometry, for the 3D viewer."""
    coords = getattr(data, "atomcoords", None) if data is not None else None
    nums = getattr(data, "atomnos", None) if data is not None else None
    if coords is None or nums is None or len(coords) == 0:
        return None
    from cclib.parser.utils import PeriodicTable

    table = PeriodicTable()
    geom = np.asarray(coords[-1], dtype=float)  # the last geometry is the optimized one (Å)
    nums = np.asarray(nums, dtype=int)
    lines = [str(len(nums)), title]
    for z, (x, y, zc) in zip(nums, geom, strict=False):
        lines.append(f"{table.element[int(z)]:2s} {x:14.6f} {y:14.6f} {zc:14.6f}")
    return Structure3D(data="\n".join(lines) + "\n", fmt="xyz", title=title, n_atoms=int(nums.size),
                       modes=_modes_from_ccdata(data))


def _modes_from_ccdata(data) -> list[VibMode]:
    """Vibrational normal modes (frequency + per-atom displacements + IR/Raman strength) for animation."""
    freqs = getattr(data, "vibfreqs", None)
    disps = getattr(data, "vibdisps", None)
    if freqs is None or disps is None:
        return []
    irs = getattr(data, "vibirs", None)
    ramans = getattr(data, "vibramans", None)
    modes: list[VibMode] = []
    for i, freq in enumerate(freqs):
        vec = np.round(np.asarray(disps[i], dtype=float), 4)
        modes.append(VibMode(
            freq=round(float(freq), 1),
            disps=[(float(x), float(y), float(z)) for x, y, z in vec],
            ir=round(float(irs[i]), 2) if irs is not None and i < len(irs) else None,
            raman=round(float(ramans[i]), 2) if ramans is not None and i < len(ramans) else None,
        ))
    return modes


def _spectrum(label: str, freqs: np.ndarray, intensities: np.ndarray, y_label: str) -> Signal:
    grid, curve = _broaden(freqs, intensities)
    return Signal(
        name=f"{label} (computed)",
        segment=label,
        x=Axis(label="Wavenumber", unit="cm⁻¹", quantity="wavenumber"),
        y=Axis(label=y_label, unit="a.u.", quantity="intensity"),
        frame=pd.DataFrame({"Wavenumber": grid, y_label: curve}),
    )


def _broaden(freqs: np.ndarray, intensities: np.ndarray, fwhm: float = 12.0, step: float = 2.0,
             pad: float = 200.0) -> tuple[np.ndarray, np.ndarray]:
    """Lorentzian-broaden a stick spectrum onto a regular wavenumber grid."""
    n = min(len(freqs), len(intensities))
    freqs, intensities = freqs[:n], intensities[:n]
    grid = np.arange(0.0, float(freqs.max()) + pad, step)
    gamma = fwhm / 2.0
    curve = np.zeros_like(grid)
    for f, inten in zip(freqs, intensities, strict=False):
        curve += inten * gamma**2 / ((grid - f) ** 2 + gamma**2)
    return grid, curve
