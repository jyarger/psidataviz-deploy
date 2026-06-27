from __future__ import annotations

import numpy as np

from psidata import Candidate
from psidata.readers.dm3_image import GatanDmReader, _stretch


def test_dm3_sniff_uses_extension_and_magic():
    r = GatanDmReader()
    assert r.sniff(Candidate(filename="x.dm3", content=b"\x00\x00\x00\x03rest")) == 0.9
    assert r.sniff(Candidate(filename="x.dm4", content=b"\x00\x00\x00\x04rest")) == 0.9
    assert r.sniff(Candidate(filename="x.dm3", content=b"junk")) == 0.8  # ext only
    assert r.sniff(Candidate(filename="x.tif", content=b"\x00\x00\x00\x03")) == 0.0


def test_stretch_maps_float_to_full_8bit_range():
    arr = np.linspace(-5.0, 1000.0, 10000).reshape(100, 100).astype("float32")
    out = _stretch(arr)
    assert out.dtype == np.uint8
    assert out.min() == 0 and out.max() == 255  # percentile stretch spans the range
