from __future__ import annotations

from psidata import Candidate, read

_ASC = (
    "EXTERNAL START\n"
    "DWELL TIME =  1000  microseconds\n"
    "PASS LENGTH =  8 \n"
    "PASS COUNT =  3000 \n"
    "CALIBRATED\n"
    "CALIBRATION UNITS = GHz \n"
    "START DATE = 12-01-94\n"
    "\n"
    "CH    0    1    3    3    4\n"   # start channel 0, then 4 counts
    "CH    4   12   10   15   31\n"   # start channel 4, then 4 counts
)


def test_brillouin_asc_reassembles_channels():
    ds = read(Candidate(filename="1MM.ASC", content=_ASC.encode(), technique_hint="Brillouin"))
    assert ds.technique == "Brillouin" and ds.source.reader == "brillouin_asc"
    sig = ds.signals[0]
    assert sig.x.label == "Channel" and sig.y.label == "Intensity"
    assert list(sig.frame["Channel"]) == [0, 1, 2, 3, 4, 5, 6, 7]
    assert list(sig.frame["Intensity"]) == [1, 3, 3, 4, 12, 10, 15, 31]
    assert ds.metadata.pass_length == 8
    assert ds.metadata.calibration_units == "GHz"
    assert str(ds.metadata.date) == "1994-12-01"


def test_brillouin_ignores_non_mcs_asc():
    from psidata.readers.brillouin_asc import BrillouinAscReader

    r = BrillouinAscReader()
    # a PerkinElmer / XRD style .asc has no MCS markers -> not claimed
    assert r.sniff(Candidate(filename="x.asc", text="10.0  100\n20.0  200\n")) == 0.0
