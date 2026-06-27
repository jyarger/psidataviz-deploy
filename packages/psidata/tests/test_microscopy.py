from __future__ import annotations

import io

import numpy as np
import pytest

from psidata import Candidate, read

PILImage = pytest.importorskip("PIL.Image")


def _png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    PILImage.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def test_microscopy_reads_image_as_photo():
    arr = (np.linspace(0, 255, 40 * 60 * 3).reshape(40, 60, 3)).astype("uint8")
    ds = read(Candidate(filename="cell.png", content=_png(arr), technique_hint="Microscopy"))
    assert ds.technique == "Microscopy"  # technique comes from the folder hint, not the reader class
    assert ds.images and ds.images[0].kind == "photo"
    assert ds.images[0].data.shape == (40, 60, 3)
    assert ds.signals == []


def test_microscopy_sniff_requires_a_microscopy_hint():
    from psidata.readers.microscopy_image import MicroscopyImageReader

    r = MicroscopyImageReader()
    img = _png(np.zeros((4, 4), "uint8"))
    assert r.sniff(Candidate(filename="x.png", content=img)) == 0.0  # no hint -> declined
    assert r.sniff(Candidate(filename="x.tif", content=img, technique_hint="SEM")) == 0.85
    # an XRD detector .tif is left to xrd_image
    assert r.sniff(Candidate(filename="x.tif", content=img, technique_hint="XRD")) == 0.0
