from __future__ import annotations

from psidata import Candidate, detect, read

_IR = (
    "# IR Spectrum\n# X-Axis:  Frequency (cm-1)\n# Y-Axis:  epsilon\n\n"
    "# Peak information\n#         X           Y\n#   1500.0    100.0\n\n"
    "# Spectrum\n1498.0 5.0\n1500.0 100.0\n1502.0 6.0\n1700.0 40.0\n"
)
_RAMAN = (
    "# Raman Activity Spectrum\n# X-Axis:  Frequency (cm-1)\n# Y-Axis:  Intensity\n\n"
    "# Spectrum\n3068.0 8.0\n3070.0 90.0\n3072.0 9.0\n"
)


def test_computed_ir_spectrum():
    cand = Candidate(filename="Acetone_Opt_Freq_DFT_B3LYP_631pd_Gaussian16_ir.txt",
                     text=_IR, technique_hint="Computational")
    assert detect(cand).name == "comp_spectrum"
    ds = read(cand)
    assert ds.technique == "Computational"
    sig = ds.signals[0]
    assert sig.x.label == "Wavenumber" and sig.x.unit == "cm⁻¹"
    assert list(sig.frame["Wavenumber"]) == [1498.0, 1500.0, 1502.0, 1700.0]
    assert ds.metadata.spectrum_type == "IR"
    assert ds.metadata.method == "B3LYP"
    assert "631" in (ds.metadata.basis_set or "")


def test_computed_raman_spectrum():
    ds = read(Candidate(filename="x_raman.txt", text=_RAMAN, technique_hint="Computational"))
    assert ds.source.reader == "comp_spectrum"
    assert ds.metadata.spectrum_type == "Raman"
    assert ds.signals[0].y.label == "Raman activity"


def test_comp_reader_ignores_plain_text():
    # an ordinary text table without the GaussView header isn't claimed
    from psidata.readers.comp_spectrum import ComputedSpectrumReader
    assert ComputedSpectrumReader().sniff(
        Candidate(filename="notes.txt", text="some experimental notes\n1 2\n3 4\n")) == 0.0


def test_comp_log_sniff_and_broaden():
    import numpy as np

    from psidata.readers.comp_log import CompLogReader, _broaden

    r = CompLogReader()
    assert r.sniff(Candidate(filename="x.log", text="...\n Entering Gaussian System ...\n")) == 0.85
    assert r.sniff(Candidate(filename="x.log", text="just a plain log\n")) == 0.0
    grid, curve = _broaden(np.array([1000.0]), np.array([100.0]))
    assert abs(float(grid[int(np.argmax(curve))]) - 1000.0) < 4.0


def test_basis_regex_stops_at_underscore():
    from psidata.readers.comp_spectrum import _method_basis

    method, basis = _method_basis("Acetone_Opt_Freq_DFT_B3LYP_631pd_Gaussian16")
    assert method == "B3LYP" and basis == "631pd"  # no trailing _Gaussian16
