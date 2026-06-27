"""Reader for **Gatan DigitalMicrograph** ``.dm3``/``.dm4`` files — TEM/STEM electron micrographs.

Gatan stores the image as a float intensity array plus a calibrated pixel size. We read it with
``ncempy``, apply a percentile contrast stretch to 8-bit, and present it as a ``photo``
:class:`~psidata.model.Image2D` (the real micrograph), like the SEM/TEM ``.tif`` path.
"""

from __future__ import annotations

import os
import tempfile

import numpy as np

from ..model import Axis, Dataset, Image2D, Metadata, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate

_DM_MAGIC = (b"\x00\x00\x00\x03", b"\x00\x00\x00\x04")  # version 3 / 4, big-endian


@register_reader
class GatanDmReader(BaseReader):
    technique = "TEM"
    name = "gatan_dm3"
    version = "0.1.0"
    extensions = (".dm3", ".dm4")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        return 0.9 if (candidate.content or b"")[:4] in _DM_MAGIC else 0.8

    def read(self, candidate: Candidate) -> Dataset:
        import ncempy.io.dm as dm

        with tempfile.NamedTemporaryFile(suffix=candidate.ext, delete=False) as tmp:
            tmp.write(candidate.content or b"")
            path = tmp.name
        try:
            parsed = dm.dmReader(path)
        finally:
            os.unlink(path)

        data = np.asarray(parsed["data"])
        if data.ndim > 2:  # a stack — show the first frame
            data = data[0]
        image = Image2D(
            name=candidate.stem,
            data=_stretch(data),
            x=Axis(label="X", unit="px", quantity="pixel"),
            y=Axis(label="Y", unit="px", quantity="pixel"),
            z=Axis(label="Intensity", unit=None, quantity="intensity"),
            kind="photo",
        )
        technique = candidate.technique_hint if (candidate.technique_hint or "").upper() in (
            "TEM", "STEM", "SEM", "MICROSCOPY") else self.technique
        return Dataset(
            technique=technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=Metadata(sample_name=candidate.stem, notes=_pixel_note(parsed)),
            images=[image],
        )


def _stretch(arr: np.ndarray) -> np.ndarray:
    """Percentile contrast-stretch a float micrograph to 8-bit for display."""
    a = np.nan_to_num(arr.astype(np.float64))
    lo, hi = np.percentile(a, (0.5, 99.5))
    if hi <= lo:
        hi = lo + 1.0
    return (np.clip((a - lo) / (hi - lo), 0.0, 1.0) * 255).astype(np.uint8)


def _pixel_note(parsed: dict) -> str | None:
    size = parsed.get("pixelSize")
    unit = parsed.get("pixelUnit")
    if size is not None and unit is not None:
        return f"{float(np.ravel(size)[0]):.3g} {np.ravel(unit)[0]}/px"
    return None
