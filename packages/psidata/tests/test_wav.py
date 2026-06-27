from __future__ import annotations

import struct

import numpy as np

from psidata import Candidate, read


def _float_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Build a minimal IEEE-float (format tag 3) mono WAV, like the real acoustic recordings."""
    data = samples.astype("<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, sample_rate, sample_rate * 4, 4, 32)
    chunks = (b"fmt " + struct.pack("<I", len(fmt)) + fmt
              + b"data" + struct.pack("<I", len(data)) + data)
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


def test_wav_reader_gives_waveform_and_fft():
    sr = 8000
    t = np.arange(sr) / sr  # 1 second
    tone = 0.5 * np.sin(2 * np.pi * 1000 * t)  # 1 kHz
    ds = read(Candidate(filename="Recorded.wav", content=_float_wav(tone, sr),
                        technique_hint="Acoustic"))
    assert ds.technique == "Acoustic" and ds.source.reader == "wav_audio"
    assert ds.audio.sample_rate == 8000 and abs(ds.audio.duration - 1.0) < 0.01
    assert [s.segment for s in ds.signals] == ["Waveform", "Spectrum (FFT)"]
    fft = ds.signals[1].frame
    peak_freq = fft.loc[fft["Magnitude"].idxmax(), "Frequency"]
    assert abs(peak_freq - 1000) < 50  # FFT peak at the tone frequency


def test_to_pcm16_wav_roundtrips():
    from psidata.readers.wav_audio import read_wav, to_pcm16_wav

    raw = _float_wav(np.linspace(-0.5, 0.5, 100), 8000)
    sr, _ch, samples = read_wav(raw)
    sr2, ch2, samples2 = read_wav(to_pcm16_wav(samples, sr))  # float -> pcm16 -> back
    assert sr2 == 8000 and ch2 == 1 and samples2.size == 100
