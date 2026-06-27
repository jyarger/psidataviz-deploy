from __future__ import annotations

from psidata import Candidate, compare_datasets, compare_record_formats, read
from psidata.sources import FileRef, build_entry, build_records


def test_same_dsc_data_as_tab_vs_comma_is_identical(dsc_txt):
    # The user's exact scenario: same DSC run saved as tab-delimited .txt and comma-delimited .csv.
    tab = read(Candidate(filename="run.txt", text=dsc_txt))
    comma = read(Candidate(filename="run.csv", text=dsc_txt.replace("\t", ",")))
    result = compare_datasets(tab, comma, a_label=".txt", b_label=".csv")
    assert result.identical, result.differences
    assert result.summary == "identical data"


def test_different_runs_report_differences(dsc_txt, dsc_csv):
    a = read(Candidate(filename="indium.txt", text=dsc_txt))        # 2 segments
    b = read(Candidate(filename="acetaminophen.csv", text=dsc_csv))  # 5 segments
    result = compare_datasets(a, b)
    assert not result.identical
    assert any("signal count" in d for d in result.differences)


def test_numeric_difference_is_detected(dsc_txt):
    a = read(Candidate(filename="run.txt", text=dsc_txt))
    b = read(Candidate(filename="run.txt", text=dsc_txt))
    # perturb one heat-flow value in b
    ycol = b.signals[0].y.label
    b.signals[0].frame.loc[0, ycol] = b.signals[0].frame.loc[0, ycol] + 5.0
    result = compare_datasets(a, b)
    assert not result.identical
    assert any("max abs diff" in d for d in result.differences)


def test_compare_record_formats_across_ascii_variants(dsc_txt):
    # a record saved as .csv and .txt (same DSC data, comma vs tab)
    entries = [
        build_entry(FileRef(path="DSC/2026_01_01_run.csv", download_url="u.csv")),
        build_entry(FileRef(path="DSC/2026_01_01_run.txt", download_url="u.txt")),
    ]
    record = build_records(entries)[0]

    def load(name, url, technique):
        text = dsc_txt if name.endswith(".txt") else dsc_txt.replace("\t", ",")
        return read(Candidate(filename=name, text=text, technique_hint=technique))

    result = compare_record_formats(record, load)
    assert result["comparable"]
    assert set(result["formats"]) == {".csv", ".txt"}
    assert all(c.get("identical") for c in result["comparisons"].values())
    assert "identical" in result["summary"]


def test_compare_record_formats_single_format_is_noop():
    record = build_records([build_entry(FileRef(path="DSC/run.csv", download_url="u"))])[0]
    result = compare_record_formats(record, load=lambda *a: None)
    assert result["comparable"] is False
