from __future__ import annotations

import pytest

from psidata import Candidate, detect, read
from psidata.readers._asdf import decode_xpp_yy
from psidata.readers.nmr_jcamp import JcampNmrReader

# Synthetic IR JCAMP with a contiguous (X++(Y..Y)) block: [10,12,14] then [16,18].
_IR_JCAMP = (
    "##TITLE=synthetic IR\n##JCAMP-DX=5.01\n##DATATYPE=INFRARED SPECTRUM\n"
    "##SPECTROMETER/DATA SYSTEM=Test FTIR\n##XUNITS=1/CM\n##YUNITS=ABSORBANCE\n"
    "##FIRSTX=400\n##LASTX=404\n##XFACTOR=1\n##YFACTOR=1\n##FIRSTY=10\n##NPOINTS=5\n"
    "##XYDATA=(X++(Y..Y))\n400A0KK\n403A6K\n##END=\n"
)


def test_ftir_jcamp_reads_infrared():
    ds = read(Candidate(filename="ir.jdx", text=_IR_JCAMP))
    assert ds.technique == "FTIR"
    assert ds.source.reader == "ftir_jcamp"
    sig = ds.signals[0]
    assert sig.x.label == "Wavenumber" and sig.x.unit == "cm⁻¹"
    assert sig.y.label == "Absorbance"
    assert list(sig.frame["Wavenumber"]) == [400, 401, 402, 403, 404]
    assert list(sig.frame["Absorbance"]) == [10, 12, 14, 16, 18]
    assert ds.metadata.instrument == "Test FTIR"


def test_nmr_reader_declines_infrared_jcamp():
    # an IR JCAMP must not be claimed by the NMR reader
    assert JcampNmrReader().sniff(Candidate(filename="ir.jdx", text=_IR_JCAMP)) == 0.0
    assert detect(Candidate(filename="ir.jdx", text=_IR_JCAMP)).technique == "FTIR"


def test_asdf_overlap_vs_contiguous_line_conventions():
    # overlap (Bruker): line 2 repeats line 1's last point; NPOINTS=4 -> drop the duplicate
    _, _, overlapped = decode_xpp_yy(["5A0KK", "3A4K"], npoints=4)
    assert overlapped == [10, 12, 14, 16]
    # contiguous (Nicolet): lines simply abut; NPOINTS=5 -> keep everything
    _, _, contiguous = decode_xpp_yy(["400A0KK", "403A6K"], npoints=5)
    assert contiguous == [10, 12, 14, 16, 18]


def test_asdf_overlap_y_value_check_raises():
    with pytest.raises(ValueError, match="Y-value check"):
        decode_xpp_yy(["5A0KK", "3A6K"], npoints=4)  # boundary 16 != 14
