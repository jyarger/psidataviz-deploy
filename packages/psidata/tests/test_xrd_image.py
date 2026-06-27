from __future__ import annotations

import numpy as np

from psidata import Candidate, read


def _edf(arr: np.ndarray, *, byteorder: str = "LowByteFirst") -> bytes:
    rows, cols = arr.shape
    header = (
        f"{{\nDim_1 = {cols} ;\nDim_2 = {rows} ;\n"
        f"DataType = FloatValue ;\nByteOrder = {byteorder} ;\n"
        "BIO_SAMPLE_NAME = watertest ;\n}\n"
    )
    order = "<" if "low" in byteorder.lower() else ">"
    return header.encode("latin1") + arr.astype(order + "f4").tobytes()


def test_read_edf_detector_image():
    arr = np.array([[1, 2, 3], [4, 5, 6]], dtype="float32")
    ds = read(Candidate(filename="frame.edf", content=_edf(arr), technique_hint="XRD"))
    assert ds.technique == "XRD" and ds.source.reader == "xrd_image"
    assert ds.signals == [] and len(ds.images) == 1
    im = ds.images[0]
    assert im.shape == (2, 3)
    np.testing.assert_array_equal(im.data, arr)
    assert im.z.label == "Intensity"
    assert ds.metadata.sample_name == "watertest"


def test_read_h5_detector_image(tmp_path):
    import h5py

    p = tmp_path / "frame.h5"
    with h5py.File(p, "w") as f:
        f.create_dataset("entry/data/data", data=np.arange(12, dtype="uint32").reshape(3, 4))
        f["entry/Metadata/Sample_Description"] = np.array([b"AuSi"])
    ds = read(Candidate(filename="frame.h5", content=p.read_bytes(), technique_hint="XRD"))
    assert ds.source.reader == "xrd_image"
    im = ds.images[0]
    assert im.shape == (3, 4)
    assert float(im.data.max()) == 11.0
    assert ds.metadata.sample_name == "AuSi"


def test_edf_not_claimed_without_brace_magic():
    from psidata.readers.xrd_image import XRDImageReader

    assert XRDImageReader().sniff(Candidate(filename="x.edf", content=b"not an edf")) == 0.0


def test_fabio_reads_written_edf_and_tif(tmp_path):
    import fabio

    arr = np.arange(12, dtype="uint16").reshape(3, 4)
    for ext, cls in [(".edf", fabio.edfimage.EdfImage), (".tif", fabio.tifimage.TifImage)]:
        p = tmp_path / f"frame{ext}"
        cls(data=arr).write(str(p))
        ds = read(Candidate(filename=f"frame{ext}", content=p.read_bytes(), technique_hint="XRD"))
        assert ds.source.reader == "xrd_image"
        assert ds.images[0].shape == (3, 4)
        np.testing.assert_array_equal(ds.images[0].data, arr)


def test_img_mccd_detected_only_with_xrd_hint():
    from psidata.readers.xrd_image import XRDImageReader

    r = XRDImageReader()
    assert r.sniff(Candidate(filename="frame.mccd", content=b"\x00\x01", technique_hint="WAXS")) == 0.8
    assert r.sniff(Candidate(filename="frame.mccd", content=b"\x00\x01", technique_hint=None)) == 0.0


def test_azimuthal_integration_recovers_a_ring():
    import math

    from psidata.readers.xrd_image import _azimuthal_integrate

    n, cx, cy = 200, 100.0, 100.0
    yy, xx = np.indices((n, n))
    r = np.hypot(xx - cx, yy - cy)
    img = np.zeros((n, n), dtype=float)
    img[(r > 49) & (r < 51)] = 1000.0  # a sharp ring at ~50 px
    geom = {"dist": 0.1, "cx": cx, "cy": cy, "pixel": 1e-4, "wavelength": 1e-10}
    sig = _azimuthal_integrate(img, geom)
    x = sig.frame["2θ"].to_numpy()
    y = sig.frame["Intensity"].to_numpy()
    peak = float(x[np.argmax(y)])
    expected = math.degrees(math.atan2(50 * 1e-4, 0.1))  # ring radius -> 2theta
    assert abs(peak - expected) < 0.2
    assert sig.x.label == "2θ" and sig.x.unit == "°"


def test_geometryless_image_has_no_1d_pattern():
    # an EDF without calibration keys -> heatmap only, no azimuthal signal
    arr = np.ones((4, 5), dtype="float32")
    ds = read(Candidate(filename="frame.edf", content=_edf(arr), technique_hint="XRD"))
    assert len(ds.images) == 1 and ds.signals == []


def test_mask_detector_gaps_and_dead_pixels():
    from psidata.readers.xrd_image import _mask_bad_pixels

    data = np.ones((100, 100), dtype="float32")  # 10,000 px of real signal = 1.0
    data[:, 50] = 4.29e9   # an inter-module gap column filled with a huge sentinel
    data[0, 0] = -1.0      # a dead/flagged pixel
    masked, n = _mask_bad_pixels(data)
    assert n >= 101  # gap column (100) + the dead pixel
    assert np.isnan(masked[5, 50]) and np.isnan(masked[0, 0])
    assert float(np.nanmax(masked)) == 1.0  # sentinel removed; real max recovered


def test_mask_leaves_clean_frame_untouched():
    from psidata.readers.xrd_image import _mask_bad_pixels

    data = np.arange(400, dtype="float32").reshape(20, 20)  # one max pixel, no gaps
    masked, n = _mask_bad_pixels(data)
    assert n == 0
    np.testing.assert_array_equal(masked, data)
