from __future__ import annotations

from psidata import Candidate, detect, read

_PE_ASC = "\n".join([
    "PE IR       SUBTECH     SPECTRUM    ASCII       PEDS        4.00",
    "   -1",
    "2026_01_01_sample.ASC",
    "26/01/01", "12:00:00.00", "26/01/02", "12:00:00.00",
    "Yarger Lab",
    "Sample 1 By YargerLab Date 2026",
    "400.0",
    "#HDR", "-1", "-1",
    "#GR", "cm-1", "%T", "1.0", "0.0", "4000.0", "-1.0", "3", "8", "100.0", "99.0",
    "#DATA",
    "4000.0\t100.5", "3999.0\t100.4", "3998.0\t100.3",
]) + "\n"


def test_pe_asc_parsed_with_header_metadata():
    ds = read(Candidate(filename="2026_01_01_sample.ASC", text=_PE_ASC))
    assert ds.technique == "FTIR" and ds.source.reader == "ftir_pe_asc"
    sig = ds.signals[0]
    assert sig.x.label == "Wavenumber" and sig.x.unit == "cm⁻¹"
    assert sig.y.label == "Transmittance" and sig.y.unit == "%T"
    assert list(sig.frame["Wavenumber"]) == [4000.0, 3999.0, 3998.0]
    assert ds.metadata.instrument == "PerkinElmer"
    assert "Sample 1" in ds.metadata.sample_name  # description recovered from header


def test_pe_asc_wins_over_generic_ftir_text_reader():
    reader = detect(Candidate(filename="x.asc", text=_PE_ASC, technique_hint="FTIR"))
    assert reader is not None and reader.name == "ftir_pe_asc"
