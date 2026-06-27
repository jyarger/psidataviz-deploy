from __future__ import annotations

from psidata import Candidate, detect, read
from psidata.readers.ftir_text import FtirTextReader
from psidata.readers.raman_text import RamanTextReader


# --- FTIR -------------------------------------------------------------------------------------
def test_ftir_dpt_detected_by_extension(ftir_dpt):
    cand = Candidate(filename="2023_06_07_CBD_powder.dpt", text=ftir_dpt)
    reader = detect(cand)
    assert reader is not None and reader.technique == "FTIR"


def test_ftir_reads_wavenumber_absorbance(ftir_dpt):
    ds = read(Candidate(filename="2023_06_07_CBD_powder.dpt", text=ftir_dpt))
    assert ds.technique == "FTIR"
    sig = ds.signals[0]
    assert sig.x.label == "Wavenumber" and sig.x.unit == "cm⁻¹"
    assert sig.y.label == "Absorbance"
    assert sig.npoints > 0
    assert ds.metadata.wavenumber_range[1] > ds.metadata.wavenumber_range[0]


# --- Raman ------------------------------------------------------------------------------------
def test_raman_csv_needs_folder_hint(raman_csv):
    # ambiguous content -> no match without the hint
    assert detect(Candidate(filename="spec.csv", text=raman_csv)) is None
    # with the Raman folder hint, it parses
    cand = Candidate(filename="spec.csv", text=raman_csv, technique_hint="Raman")
    reader = detect(cand)
    assert reader is not None and reader.technique == "Raman"


def test_raman_multiple_accumulations_become_signals(raman_csv):
    ds = read(Candidate(filename="spec.csv", text=raman_csv, technique_hint="Raman"))
    assert ds.technique == "Raman"
    # fixture has shift + 3 intensity columns
    assert len(ds.signals) == 3
    assert ds.metadata.n_traces == 3
    sig = ds.signals[0]
    assert sig.x.label == "Raman shift" and sig.x.unit == "cm⁻¹"
    assert sig.y.label == "Intensity"
    # Raman shift ascends
    assert sig.frame["Raman shift"].iloc[0] < sig.frame["Raman shift"].iloc[-1]


def test_raman_sidecar_metadata_is_ignored():
    # the tiny *_spec.txt sidecars carry no numeric table
    tiny = "Center: 977\nGrating: 600\nLaser: 532nm\n"
    assert RamanTextReader().sniff(Candidate(filename="x_spec.txt", text=tiny,
                                             technique_hint="Raman")) == 0.0


def test_dsc_csv_not_claimed_by_raman_in_dsc_folder(dsc_csv):
    # a DSC export carried under a DSC hint must not be grabbed by Raman
    assert RamanTextReader().sniff(Candidate(filename="run.csv", text=dsc_csv,
                                             technique_hint="DSC")) == 0.0
    assert FtirTextReader().sniff(Candidate(filename="run.csv", text=dsc_csv,
                                            technique_hint="DSC")) == 0.0
    assert read(Candidate(filename="run.csv", text=dsc_csv, technique_hint="DSC")).technique == "DSC"


def test_parse_raman_spec_sidecar():
    from psidata.readers.raman_text import parse_spec_sidecar

    d = parse_spec_sidecar("Green\r\n12.0mW\r\nAndor750 (3)\r\nPolarized\r\n")
    assert d == {"laser": "Green", "laser_power_mw": 12.0,
                 "spectrometer": "Andor750 (3)", "polarization": "Polarized"}


def test_opus_sniff_and_block_pick():
    from psidata.readers.ftir_opus import FtirOpusReader, _pick_block

    r = FtirOpusReader()
    assert r.sniff(Candidate(filename="x.0", content=b"\n\n\xfe\xfe more")) == 0.95
    assert r.sniff(Candidate(filename="x.0", content=b"not an opus file")) == 0.0
    assert r.sniff(Candidate(filename="x.dpt", content=b"\n\n\xfe\xfe")) == 0.0  # wrong ext
    assert _pick_block({"AB": [1, 2]}) == ("AB", "Absorbance", "absorbance")
