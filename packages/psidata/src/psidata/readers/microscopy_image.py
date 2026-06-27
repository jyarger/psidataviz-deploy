"""Readers for **microscopy images** — SEM, TEM, and optical/polarized-light microscopy.

These are micrographs (the pixels *are* the data — grayscale electron images, or colour polarized-light
images), so they're carried as a ``photo`` :class:`~psidata.model.Image2D` and shown as the real image,
not a false-colour heatmap. Pillow reads ``.tif``/``.jpg``/``.png``/``.bmp``. (Gatan ``.dm3``/``.ser`` TEM
formats are a planned follow-up.)
"""

from __future__ import annotations

import io

import numpy as np

from ..model import Axis, Dataset, Image2D, Metadata, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate

_IMAGE_EXTS = (".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp")
_MICRO_HINTS = {"SEM", "TEM", "STEM", "MICROSCOPY", "OPTICAL", "EM"}


class _MicroscopyImageReader(BaseReader):
    """Shared logic; concrete subclasses bind a technique (so the catalog matches the folder)."""

    extensions = _IMAGE_EXTS

    def sniff(self, candidate: Candidate) -> float:
        # Image files are claimed only in a microscopy context (the folder/technique hint) — this keeps
        # stray preview .jpg/.png and XRD detector .tif out. The catalog still matches by folder via
        # _match_reader (which ignores sniff), so SEM/TEM/Microscopy images scan as supported.
        if candidate.ext not in self.extensions:
            return 0.0
        return 0.85 if (candidate.technique_hint or "").upper() in _MICRO_HINTS else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        from PIL import Image as PILImage

        arr = np.asarray(PILImage.open(io.BytesIO(candidate.content or b"")))
        if arr.ndim == 3 and arr.shape[2] == 4:  # drop alpha
            arr = arr[..., :3]
        image = Image2D(
            name=candidate.stem,
            data=arr,
            x=Axis(label="X", unit="px", quantity="pixel"),
            y=Axis(label="Y", unit="px", quantity="pixel"),
            z=Axis(label="Intensity", unit=None, quantity="intensity"),
            kind="photo",
        )
        # the three image readers share one sniff, so the registry may pick any; honour the folder's
        # technique hint (SEM/TEM/Microscopy) so the dataset is labelled correctly.
        hint = candidate.technique_hint
        technique = hint if (hint or "").upper() in _MICRO_HINTS else self.technique
        return Dataset(
            technique=technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=Metadata(sample_name=candidate.stem),
            images=[image],
        )


@register_reader
class SemImageReader(_MicroscopyImageReader):
    technique = "SEM"
    name = "sem_image"
    version = "0.1.0"


@register_reader
class TemImageReader(_MicroscopyImageReader):
    technique = "TEM"
    name = "tem_image"
    version = "0.1.0"


@register_reader
class MicroscopyImageReader(_MicroscopyImageReader):
    technique = "Microscopy"
    name = "microscopy_image"
    version = "0.1.0"
