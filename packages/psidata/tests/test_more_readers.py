"""Tests for the breadth readers: dielectric, HPLC, JCAMP mass-spec, and CD .dcs."""
from __future__ import annotations

from psidata import Candidate, read

DIELECTRIC = "f / Hz,T=300.00K,T=290.00K\n1000,0.50,0.60\n2000,0.40,0.50\n4000,0.30,0.40\n"

HPLC = "0.10, 1.0\n0.20, 2.0\n0.30, 3.0\n0.40, 2.5\n"

MS_JCAMP = """##TITLE=terpyridine
##JCAMP-DX=5.00
##DATA TYPE=MASS SPECTRUM
##DATA CLASS=NTUPLES
##NTUPLES=MASS SPECTRUM
##PAGE=1
##NPOINTS=2
##DATA TABLE= (XY..XY), PEAKS
100.0, 50.0
200.0, 75.0
##PAGE=2
##NPOINTS=1
##DATA TABLE= (XY..XY), PEAKS
150.0, 25.0
##END=
"""

CD_DCS = """@!NAME:test sample
@!MIN:189.00
@!MAX:270.00
>examp_1.dat
270\t-0.10
269\t-0.20
268\t-0.30
>examp_1.dat-2
270\t-0.15
269\t-0.25
"""


def test_dielectric_reads_temperature_columns():
    ds = read(Candidate(filename="CBD-Eps-Imag.dat", content=DIELECTRIC.encode(), technique_hint="Dielectric"))
    assert ds.source.reader == "dielectric_text"
    assert ds.technique == "Dielectric"
    assert len(ds.signals) == 2  # one per temperature column
    s = ds.signals[0]
    assert s.segment == "T=300.00K"
    assert (s.x.label, s.x.unit) == ("Frequency", "Hz")
    assert s.y.label.startswith("ε")  # ε″ for the Imag file
    assert list(s.frame["Frequency"]) == [1000.0, 2000.0, 4000.0]


def test_hplc_reads_only_with_context():
    from psidata.readers.hplc_text import HplcTextReader

    r = HplcTextReader()
    assert r.sniff(Candidate(filename="trace.csv", content=HPLC.encode())) == 0.0  # no HPLC context
    ds = read(Candidate(filename="sample_HPLCdata.csv", content=HPLC.encode(), technique_hint="HPLC"))
    assert ds.source.reader == "hplc_text"
    assert ds.technique == "HPLC"
    assert (ds.signals[0].x.label, ds.signals[0].x.unit) == ("Retention time", "min")
    assert len(ds.signals[0].frame) == 4


def test_jcamp_mass_spec_merges_pages_sorted():
    ds = read(Candidate(filename="ms.jdx", content=MS_JCAMP.encode(), technique_hint="Mass Spec"))
    assert ds.source.reader == "jcamp_ms"
    assert ds.technique == "Mass Spec"
    s = ds.signals[0]
    assert s.x.label == "m/z"
    assert list(s.frame["m/z"]) == [100.0, 150.0, 200.0]  # both pages merged, sorted by m/z
    assert "2 scan" in (ds.metadata.notes or "")


def test_cd_dcs_reads_first_section_only():
    ds = read(Candidate(filename="hewl_far_UV.dcs", content=CD_DCS.encode(), technique_hint="CD"))
    assert ds.source.reader == "cd_dcs"
    assert ds.technique == "CD"
    s = ds.signals[0]
    assert (s.x.label, s.x.unit) == ("Wavelength", "nm")
    assert len(s.frame) == 3  # only the first ">" section, not the replicate
    assert ds.metadata.sample_name == "test sample"
    assert "2 replicate" in (ds.metadata.notes or "")


def _xlsx(rows: list[list], sheet: str = "Sheet1") -> bytes:
    import io

    import pandas as pd
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame(rows).to_excel(w, header=False, index=False, sheet_name=sheet)
    return buf.getvalue()


def test_spreadsheet_reader_extracts_xy_and_uses_hint():
    rows = [["Time", "Strain", "Stress"], ["s", "mm/mm", "MPa"]]
    rows += [[float(i) * 0.1, i * 0.001, i * 5.0] for i in range(20)]  # >=10 data rows
    ds = read(Candidate(filename="run.xlsx", content=_xlsx(rows, "Test 1"), technique_hint="Mechanical"))
    assert ds.source.reader == "spreadsheet_table"
    assert ds.technique == "Mechanical"  # from the folder hint, not the reader class
    assert (ds.signals[0].x.label, ds.signals[0].x.unit) == ("Time", "s")
    ylabels = {(s.y.label, s.y.unit) for s in ds.signals}
    assert ("Stress", "MPa") in ylabels and ("Strain", "mm/mm") in ylabels


def test_spreadsheet_reader_declines_categorical_summary():
    from psidata.readers.spreadsheet_table import SpreadsheetReader

    rows = [["Amino acid", "Sample"], *[["His", "high"], ["Ser", "low"], ["Arg", "mid"]]]
    cand = Candidate(filename="summary.xlsx", content=_xlsx(rows))
    assert SpreadsheetReader().sniff(cand) == 0.0  # no numeric x/y table -> declined


def test_jcamp_sims_labelled_distinctly_from_ms():
    # the same JCAMP mass-spectrum format, but a SIMS hint -> SIMS technique (not standard Mass Spec)
    sims = read(Candidate(filename="surface.itax.peak.jdx", content=MS_JCAMP.encode(),
                          technique_hint="SIMS"))
    assert sims.technique == "SIMS"
    ms = read(Candidate(filename="ms.jdx", content=MS_JCAMP.encode(), technique_hint="Mass Spec"))
    assert ms.technique == "Mass Spec"


def test_catalog_splits_sims_from_mass_spec():
    from psidata.sources.catalog import _refine_subtechnique

    assert _refine_subtechnique("Mass Spec", "Sample_ZnO_SIMS.zip") == "SIMS"
    assert _refine_subtechnique("Mass Spec", "Terpyridine_FeCl3_MS.zip") == "Mass Spec"
    assert _refine_subtechnique("Raman", "thing_sims_extra.txt") == "Raman"  # only refines MS folders
