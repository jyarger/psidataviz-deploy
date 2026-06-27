from __future__ import annotations

from psidata import Candidate, read


def test_acoustic_spectrum_reads_frequency_magnitude():
    csv = "Frequency (Hz),FFT Magnitude (dB)\n0.00,-120.000\n0.98,-88.511\n1.95,-88.088\n"
    ds = read(Candidate(filename="Air_16kHz_Spectrum.csv", content=csv.encode(),
                        technique_hint="Acoustic"))
    assert ds.technique == "Acoustic" and ds.source.reader == "acoustic_spectrum"
    sig = ds.signals[0]
    assert sig.x.label == "Frequency" and sig.x.unit == "Hz"
    assert sig.y.label == "FFT Magnitude" and sig.y.unit == "dB"
    assert list(sig.frame["Frequency"]) == [0.0, 0.98, 1.95]
    assert ds.metadata.sample_name == "Air_16kHz"


def test_acoustic_ignores_sibling_sensor_csv():
    from psidata.readers.acoustic_spectrum import AcousticSpectrumReader

    r = AcousticSpectrumReader()
    sensor = "Time (s),Temperature (C),Pressure (kPa)\n0,25,101\n"
    # the SensorsData.csv has no frequency/magnitude header -> not claimed as the spectrum
    assert r.sniff(Candidate(filename="x_SensorsData.csv", text=sensor)) == 0.0
