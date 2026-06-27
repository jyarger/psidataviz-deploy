from __future__ import annotations

from pathlib import Path

from psidata import Candidate, detect, read

FIXTURES = Path(__file__).parent / "fixtures"


# --- plain ppm/intensity .tsv -----------------------------------------------------------------
def test_nmr_tsv_reads_ppm_intensity():
    tsv = "x\ty\n10.0\t100\n9.5\t250\n9.0\t120\n8.5\t90\n"
    ds = read(Candidate(filename="2026_05_10_aspirin_cdcl3_tms_bruker500_13C.tsv",
                        text=tsv, technique_hint="NMR"))
    assert ds.technique == "NMR" and ds.source.reader == "nmr_text"
    assert ds.metadata.nucleus == "13C"  # recovered from the filename
    sig = ds.signals[0]
    assert sig.x.label == "Chemical shift" and sig.x.unit == "ppm"
    assert list(sig.frame["Intensity"]) == [100, 250, 120, 90]


def test_nmr_tsv_needs_folder_hint():
    tsv = "x\ty\n10\t1\n9\t2\n"
    assert detect(Candidate(filename="x.tsv", text=tsv)) is None  # ambiguous without the hint


# --- 2D TopSpin totxt -------------------------------------------------------------------------
def test_nmr_totxt_2d_becomes_multisignal():
    text = (FIXTURES / "nmr_cpmg_totxt_trimmed.txt").read_text(encoding="utf-8")
    ds = read(Candidate(filename="2022_10_28_CBD_FS_3mm_1H_298K_CPMG.txt", text=text))
    assert ds.technique == "NMR" and ds.source.reader == "nmr_totxt"
    assert len(ds.signals) == 3                       # one spectrum per F1 row
    assert ds.metadata.extra["n_rows"] == 3
    sig = ds.signals[0]
    assert sig.npoints == 40 and sig.x.label == "Chemical shift" and sig.x.unit == "ppm"
    # F2 axis runs from F2LEFT (~130) down to F2RIGHT (~-120) ppm
    assert sig.frame["Chemical shift"].iloc[0] > sig.frame["Chemical shift"].iloc[-1]


def test_totxt_does_not_claim_plain_text():
    assert detect(Candidate(filename="notes.txt", text="just text\nno markers\n")) is None
