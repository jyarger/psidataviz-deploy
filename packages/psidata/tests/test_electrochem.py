from __future__ import annotations

from psidata import Candidate, read

GAMRY_DTA = """EXPLAIN
TAG\tCV
TITLE\tLABEL\tCyclic Voltammetry\tTest &Identifier
DATE\tLABEL\t11.6.2025\tDate
PSTAT\tPSTAT\tIFC1010-XYZ\tPotentiostat
SCANRATE\tQUANT\t9,99998E+001\t&Scan Rate (mV/s)
CURVE1\tTABLE
\tPt\tT\tVf\tIm\tVu
\t#\ts\tV vs. Ref.\tA\tV
\t0\t0,02\t1,00000E-001\t1,00000E-006\t0,00000E+000
\t1\t0,04\t2,00000E-001\t2,00000E-006\t0,00000E+000
\t2\t0,06\t3,00000E-001\t3,00000E-006\t0,00000E+000
"""

CV_JCAMP = """##TITLE=Spectrum
##JCAMP-DX=5.00 $$ chemotion-converter-app (1.5.0)
##DATA TYPE=CYCLIC VOLTAMMETRY
##DATA CLASS=XYPOINTS
##XUNITS=Voltage in V
##YUNITS=Current in A
##DATE=11.6.2025
##SERIAL=IFC1010-XYZ
##XYPOINTS=(XY..XY)
0.10 1.0E-6
0.20 2.0E-6
0.30 3.0E-6
##END=
"""


def test_gamry_dta_reads_cv_with_comma_decimals():
    ds = read(Candidate(filename="cell_CV.DTA", content=GAMRY_DTA.encode(), technique_hint="Electrochem"))
    assert ds.source.reader == "gamry_dta"
    assert ds.technique == "Electrochem"
    s = ds.signals[0]
    assert (s.x.label, s.x.unit) == ("Potential", "V")
    assert (s.y.label, s.y.unit) == ("Current", "A")
    assert list(s.frame["Potential"]) == [0.1, 0.2, 0.3]  # comma decimals decoded
    assert s.frame["Current"].iloc[2] == 3.0e-6
    assert ds.metadata.date and ds.metadata.date.isoformat() == "2025-06-11"


def test_chemotion_jcamp_cv_reads_as_electrochem_not_nmr():
    ds = read(Candidate(filename="table_01.jdx", content=CV_JCAMP.encode(), technique_hint="Electrochem"))
    assert ds.source.reader == "jcamp_electrochem"  # not nmr_jcamp
    assert ds.technique == "Electrochem"
    s = ds.signals[0]
    assert (s.x.label, s.x.unit) == ("Potential", "V")  # from ##XUNITS=Voltage in V
    assert (s.y.label, s.y.unit) == ("Current", "A")
    assert ds.metadata.instrument == "IFC1010-XYZ"


def test_nmr_jcamp_declines_voltammetry():
    from psidata.readers.nmr_jcamp import JcampNmrReader

    cand = Candidate(filename="table_01.jdx", content=CV_JCAMP.encode())
    assert JcampNmrReader().sniff(cand) == 0.0
