from __future__ import annotations

import numpy as np
import pytest

from psidata import Candidate, detect, read
from psidata.readers.nmr_jcamp import JcampNmrReader, NMRMetadata


def _candidate(nmr_txt: str) -> Candidate:
    return Candidate(filename="2024_05_17_EC_Samples_1H_Adamantane_Ref.txt", text=nmr_txt,
                     uri="https://example/NMR/adamantane.txt")


def test_detects_nmr_jcamp_over_dsc(nmr_txt):
    reader = detect(_candidate(nmr_txt))
    assert reader is not None and reader.name == "nmr_jcamp"


def test_dsc_text_does_not_match_nmr(dsc_txt):
    # a DSC export must not be claimed by the NMR reader
    assert JcampNmrReader().sniff(Candidate(filename="run.txt", text=dsc_txt)) == 0.0


def test_reads_metadata(nmr_txt):
    ds = read(_candidate(nmr_txt))
    assert ds.technique == "NMR"
    assert isinstance(ds.metadata, NMRMetadata)
    m = ds.metadata
    assert m.nucleus == "1H"
    assert m.frequency_mhz == pytest.approx(399.7394556)
    assert "Adamantane" in m.sample_name


def test_parses_xy_pairs(nmr_txt):
    ds = read(_candidate(nmr_txt))
    assert len(ds.signals) == 1
    sig = ds.signals[0]
    assert sig.x.label == "Chemical shift"
    assert sig.x.unit == "ppm"
    assert sig.y.label == "Intensity"
    assert sig.npoints == 80
    # ppm axis runs high -> low in the file
    assert sig.frame["Chemical shift"].iloc[0] > sig.frame["Chemical shift"].iloc[-1]


# A tiny hand-encoded (X++(Y..Y)) block exercising SQZ / DIF(+,-,0) / DUP.
# "6A0Lk%UN" -> leadX=6, ordinates [10, 13, 11, 11, 11, 11, 16].
_ASDF = (
    "##TITLE=synthetic compressed\n##JCAMP-DX=5.01\n##DATA TYPE= NMR SPECTRUM\n"
    "##.OBSERVE NUCLEUS= ^13C\n##.OBSERVE FREQUENCY= 125.0\n"
    "##XUNITS=HZ\n##XFACTOR=1\n##YFACTOR=1\n##FIRSTX=0\n##LASTX=6\n"
    "##NPOINTS=7\n##FIRSTY=10\n##XYDATA=(X++(Y..Y))\n6A0Lk%UN\n##END=\n"
)


def test_decodes_compressed_asdf():
    ds = read(Candidate(filename="bruker.jdx", text=_ASDF))
    assert ds.technique == "NMR"
    sig = ds.signals[0]
    assert sig.npoints == 7
    assert list(sig.frame["Intensity"]) == [10, 13, 11, 11, 11, 11, 16]
    assert list(sig.frame["Frequency"]) == [6, 5, 4, 3, 2, 1, 0]
    assert sig.x.unit == "Hz"
    assert ds.metadata.nucleus == "13C"


def test_asdf_tolerates_mismatched_npoints():
    # Real exports (e.g. edited Chemotion JCAMP) sometimes disagree with the header NPOINTS via
    # mixed/duplicated line boundaries. Rather than reject the spectrum, we de-overlap adaptively and
    # decode the ordinates that are actually present.
    bad = _ASDF.replace("##NPOINTS=7", "##NPOINTS=99")
    ds = read(Candidate(filename="bruker.jdx", text=bad))
    assert ds.signals and ds.signals[0].npoints == 7


# A tiny NTUPLES NMR FID (Nanalysis NMReady style): REAL + IMAG pages, decayed so the FFT is well
# defined. SF/SWH/O1P drive the ppm axis (SW=SWH/SF=7 ppm, OFFSET=O1P+SW/2=8.5).
_NTUPLES_FID = (
    "##TITLE=synthetic fid\n##JCAMP-DX=5.01 $$ Nanalysis NMReady\n"
    "##DATA TYPE=NMR FID\n##DATA CLASS=NTUPLES\n"
    "##.OBSERVE NUCLEUS=^1H\n##.OBSERVE FREQUENCY=100.0\n##.SOLVENT NAME=Chloroform-d\n"
    "##$SF= 100.0\n##$SWH= 700.0\n##$O1P= 5.0\n##NPOINTS=7\n"
    "##NTUPLES=NMR FID\n##VAR_NAME=TIME,FID/REAL,FID/IMAG,PAGE NUMBER\n"
    "##SYMBOL=X,R,I,N\n##VAR_DIM=7,7,7,2\n##FACTOR=1,1,1,1\n"
    "##PAGE=N=1\n##DATA TABLE= (X++(R..R)), XYDATA\n0 100 60 30 10 5 2 1\n"
    "##PAGE=N=2\n##DATA TABLE= (X++(I..I)), XYDATA\n0 0 20 15 8 4 2 1\n"
    "##END NTUPLES=NMR FID\n##END=\n"
)


def test_ntuples_fid_is_fourier_transformed_to_spectrum():
    cand = Candidate(filename="NMR_synthetic_NAnalysis60.dx", text=_NTUPLES_FID, technique_hint="NMR")
    assert detect(cand).name == "nmr_jcamp"
    ds = read(cand)
    assert ds.technique == "NMR"
    sig = ds.signals[0]
    assert sig.npoints == 7  # SI not set -> spectrum length == FID length
    assert sig.x.label == "Chemical shift" and sig.x.unit == "ppm"
    cs = sig.frame["Chemical shift"].to_numpy()
    assert cs[0] == pytest.approx(8.5) and cs[-1] == pytest.approx(2.5)  # OFFSET -> OFFSET-SW
    assert (sig.frame["Intensity"].to_numpy() >= 0).all()  # magnitude spectrum
    assert "FID" in ds.metadata.data_type and "spectrum" in ds.metadata.data_type
    assert ds.metadata.nucleus == "1H" and ds.metadata.solvent == "Chloroform-d"


def test_ntuples_non_fid_is_declined():
    # an NTUPLES class we don't decode must not be claimed as "supported"
    spectrum = (
        "##TITLE=x\n##JCAMP-DX=5.01\n##DATA TYPE=NMR SPECTRUM\n##DATA CLASS=NTUPLES\n"
        "##.OBSERVE NUCLEUS=^1H\n##NTUPLES=NMR SPECTRUM\n##END=\n"
    )
    assert JcampNmrReader().sniff(Candidate(filename="x.dx", text=spectrum)) == 0.0


_NMR_2D = (
    "##TITLE=synthetic 2d\n##JCAMP-DX=6.0\n##DATA TYPE=nD NMR SPECTRUM\n##DATA CLASS=NTUPLES\n"
    "##NUMDIM=2\n##.OBSERVE FREQUENCY=100.0, 400.0\n##.NUCLEUS=13C, 1H\n"
    "##NTUPLES=nD NMR SPECTRUM\n##VAR_NAME=FREQUENCY1, FREQUENCY2, SPECTRUM\n##SYMBOL=F1, F2, Y\n"
    "##VAR_FORM=AFFN, AFFN, ASDF\n##VAR_DIM=2, 3, 6\n##UNITS=HZ, HZ, ARBITRARY UNITS\n"
    "##FIRST=4000, 1200, 10\n##LAST=2000, 400, 60\n##FACTOR=1, 1, 1\n"
    "##PAGE=F1=4000\n##DATA TABLE=(F2++(Y..Y)), PROFILE\n1200 10 20 30\n"
    "##PAGE=F1=2000\n##DATA TABLE=(F2++(Y..Y)), PROFILE\n1200 40 50 60\n"
    "##END NTUPLES=nD NMR SPECTRUM\n##END=\n"
)


def test_reads_2d_nmr_ntuples_as_contour_map():
    cand = Candidate(filename="LBU_HSQC.jdx", text=_NMR_2D, technique_hint="NMR")
    assert detect(cand).name == "nmr_2d_jcamp"  # wins over the 1D nmr_jcamp reader
    ds = read(cand)
    assert ds.technique == "NMR" and not ds.signals and len(ds.images) == 1
    im = ds.images[0]
    assert im.kind == "nmr2d" and im.data.shape == (2, 3)
    assert im.x.unit == "ppm" and im.y.unit == "ppm"  # Hz / observe-frequency
    np.testing.assert_allclose(im.x_values, [3.0, 2.0, 1.0])  # F2 (1H): 1200,800,400 / 400
    np.testing.assert_allclose(im.y_values, [40.0, 20.0])     # F1 (13C): 4000,2000 / 100
    assert im.data[1, 2] == 60
