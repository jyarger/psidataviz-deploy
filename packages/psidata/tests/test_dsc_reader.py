from __future__ import annotations

from datetime import date

from psidata import Candidate, read
from psidata.readers.dsc_trios import DSCMetadata, DscTriosReader


def _candidate(dsc_txt: str) -> Candidate:
    return Candidate(filename="2023_06_14_Indium_wire_std.txt", text=dsc_txt,
                     uri="https://example/DSC/2023_06_14_Indium_wire_std.txt")


def test_reads_metadata(dsc_txt):
    ds = DscTriosReader().read(_candidate(dsc_txt))
    assert ds.technique == "DSC"
    assert isinstance(ds.metadata, DSCMetadata)
    m = ds.metadata
    assert m.sample_name == "2023_06_14_Indium_wire_std"
    assert m.date == date(2023, 6, 14)
    assert m.operator == "SBK"
    assert m.instrument == "DSC2500"
    assert m.sample_mass_mg == 20.72
    assert m.pan_type == "Aluminum Hermetic"
    assert m.exotherm_direction == "Down"
    assert m.method_log  # non-empty list
    assert m.available_signals  # [Signal List] captured


def test_parses_two_segments(dsc_txt):
    ds = DscTriosReader().read(_candidate(dsc_txt))
    assert len(ds.signals) == 2
    assert ds.metadata.n_segments == 2
    first = ds.signals[0]
    assert "Ramp" in first.segment
    # x defaults to Temperature, y to Heat Flow
    assert first.x.quantity == "temperature"
    assert first.x.unit == "°C"
    assert first.y.quantity == "heat_flow"
    assert "Heat Flow" in first.y.label
    assert first.npoints > 0


def test_data_values_are_numeric_and_sane(dsc_txt):
    ds = DscTriosReader().read(_candidate(dsc_txt))
    df = ds.signals[0].frame
    assert {"Time", "Temperature"}.issubset(df.columns)
    # Indium first ramp starts near 120 C
    assert 115 < df["Temperature"].iloc[0] < 125
    assert df["Temperature"].is_monotonic_increasing or df["Temperature"].iloc[-1] > df["Temperature"].iloc[0]


def test_read_via_registry_autodetect(dsc_txt):
    ds = read(_candidate(dsc_txt))
    assert ds.technique == "DSC"


def _csv_candidate(dsc_csv: str) -> Candidate:
    return Candidate(filename="2026_05_26_Acetaminophen_n60C_200C_2Cmin_x2_DSC.csv", text=dsc_csv,
                     uri="https://example/DSC/acetaminophen.csv")


def test_reads_modern_comma_delimited_csv(dsc_csv):
    ds = read(_csv_candidate(dsc_csv))  # registry auto-detects + parses
    assert ds.technique == "DSC"
    m = ds.metadata
    assert m.sample_name == "2026_05_26_Acetaminophen_n60C_200C_2Cmin_x2_DSC"
    assert m.date == date(2026, 5, 27)
    assert m.operator == "JLY"
    assert m.instrument == "DSC2500"
    assert m.sample_mass_mg == 5.61
    assert m.exotherm_direction == "Down"


def test_csv_segments_and_numeric_data(dsc_csv):
    ds = read(_csv_candidate(dsc_csv))
    assert len(ds.signals) == 5  # this run has 5 ramp segments
    df = ds.signals[0].frame
    assert list(df.columns) == ["Time", "Temperature", "Heat Flow (Normalized)"]
    # first ramp starts near -60 C
    assert -65 < df["Temperature"].iloc[0] < -55
    assert ds.signals[0].x.quantity == "temperature"
    assert ds.signals[0].y.quantity == "heat_flow"


def test_txt_and_csv_use_same_columns(dsc_txt, dsc_csv):
    txt = read(Candidate(filename="run.txt", text=dsc_txt))
    csv = read(Candidate(filename="run.csv", text=dsc_csv))
    assert list(txt.signals[0].frame.columns) == list(csv.signals[0].frame.columns)


def test_tidy_and_summary(dsc_txt):
    ds = read(_candidate(dsc_txt))
    tidy = ds.to_tidy_df()
    assert {"signal", "segment", "Temperature"}.issubset(tidy.columns)
    summary = ds.summary()
    assert summary["technique"] == "DSC"
    assert summary["n_signals"] == 2
    assert ds.source.reader == "dsc_trios"
