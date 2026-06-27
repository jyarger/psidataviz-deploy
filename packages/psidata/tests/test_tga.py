from __future__ import annotations

from psidata import Candidate, read

# a minimal TA Instruments TGA export (degree sign as cp437 byte 0xF8, like the real files)
_TGA = (
    "Instrument\t2950 TGA V5.4A\n"
    "Module\tTGA 1000 \xb0C\n"
    "Sample\tCuSO4_5Hydrate\n"
    "Size\t10.0\tmg\n"
    "Method\t25C to 350C at 10 cpm\n"
    "Operator\tJLY\n"
    "Xcomment\tPan: Platinum  Gas1: Nitrogen 40\n"
    "Nsig\t3\n"
    "Sig1\tTime (min)\n"
    "Sig2\tTemperature (\xb0C)\n"
    "Sig3\tWeight (mg)\n"
    "Date\t12-Jul-23\n"
    "StartOfData\n"
    "0.0\t25.0\t10.0\n"
    "1.0\t100.0\t9.0\n"
    "2.0\t200.0\t6.5\n"
)


def test_tga_reader_weight_percent_and_metadata():
    ds = read(Candidate(filename="2023_07_12_CuSO4_TGA.txt",
                        content=_TGA.encode("cp437"), technique_hint="TGA"))
    assert ds.technique == "TGA" and ds.source.reader == "tga_text"
    sig = ds.signals[0]
    assert sig.x.label == "Temperature" and sig.x.unit == "°C"  # cp437 0xF8 -> degree
    assert sig.y.label == "Weight" and sig.y.unit == "%"
    # normalized to the first point: 10 mg = 100 %, 6.5 mg = 65 %
    assert list(sig.frame["Weight"]) == [100.0, 90.0, 65.0]
    assert list(sig.frame["Temperature"]) == [25.0, 100.0, 200.0]
    assert ds.metadata.sample_mass_mg == 10.0
    assert ds.metadata.sample_name == "CuSO4_5Hydrate"
    assert ds.metadata.method == "25C to 350C at 10 cpm"


def test_tga_reader_ignores_dsc_and_non_tga_txt():
    from psidata.readers.tga_text import TgaTextReader

    r = TgaTextReader()
    # a DSC StartOfData file has Heat Flow, not Weight -> not claimed by the TGA reader
    dsc = "Instrument\tDSC\nNsig\t2\nSig1\tTemperature\nSig2\tHeat Flow\nStartOfData\n1\t2\n"
    assert r.sniff(Candidate(filename="x.txt", text=dsc)) == 0.0
    assert r.sniff(Candidate(filename="x.txt", text="just a text file")) == 0.0
