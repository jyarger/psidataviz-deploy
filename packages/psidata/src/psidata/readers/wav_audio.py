"""Reader for ``.wav`` audio — acoustic-interferometry recordings.

Produces two views as ordinary signals — the **time-domain waveform** and its **FFT spectrum** — plus
:class:`~psidata.model.Audio` playback parameters. A manual RIFF parse handles both integer PCM and
IEEE-float WAV (Python's ``wave`` module can't read float), and :func:`to_pcm16_wav` re-encodes to
plain 16-bit PCM so any browser can play it.
"""

from __future__ import annotations

import io
import struct
import wave

import numpy as np
import pandas as pd

from ..model import Audio, Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate

_PLOT_POINTS = 4000


@register_reader
class WavAudioReader(BaseReader):
    technique = "Acoustic"
    name = "wav_audio"
    version = "0.1.0"
    extensions = (".wav",)

    def sniff(self, candidate: Candidate) -> float:
        content = candidate.content or b""
        return 0.9 if content[:4] == b"RIFF" and content[8:12] == b"WAVE" else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        sample_rate, channels, samples = read_wav(candidate.content or b"")
        if samples.size == 0:
            raise ValueError(f"{candidate.filename}: empty audio")
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=Metadata(sample_name=candidate.stem),
            signals=[_waveform_signal(samples, sample_rate), _fft_signal(samples, sample_rate)],
            audio=Audio(sample_rate=sample_rate, n_samples=int(samples.size), channels=channels),
        )


def read_wav(raw: bytes) -> tuple[int, int, np.ndarray]:
    """Parse a WAV (PCM int or IEEE float) into ``(sample_rate, channels, mono float samples)``."""
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(raw):
        chunk_id = raw[pos:pos + 4]
        size = struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if chunk_id == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])  # tag, channels, rate, byte-rate, block, bits
        elif chunk_id == b"data":
            data = body
        pos += 8 + size + (size & 1)  # chunks are word-aligned
    if fmt is None or data is None:
        raise ValueError("WAV missing fmt/data chunk")
    tag, channels, rate, _byterate, _block, bits = fmt
    if tag == 3:  # IEEE float
        samples = np.frombuffer(data, dtype=np.float32 if bits == 32 else np.float64).astype(np.float64)
    elif tag in (1, 0xFFFE):  # integer PCM (0xFFFE = extensible; assume PCM)
        dtype = {8: np.uint8, 16: np.int16, 32: np.int32}.get(bits)
        if dtype is None:
            raise ValueError(f"unsupported PCM bit depth {bits}")
        samples = np.frombuffer(data, dtype=dtype).astype(np.float64)
        samples = (samples - 128) / 128.0 if bits == 8 else samples / float(2 ** (bits - 1))
    else:
        raise ValueError(f"unsupported WAV format tag {tag}")
    if channels > 1:
        samples = samples[: samples.size - samples.size % channels].reshape(-1, channels).mean(axis=1)
    return int(rate), int(channels), samples


def to_pcm16_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Re-encode mono float samples as 16-bit PCM WAV bytes (universally playable in browsers)."""
    int16 = np.clip(samples, -1.0, 1.0)
    int16 = (int16 * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(int16.tobytes())
    return buf.getvalue()


def _waveform_signal(samples: np.ndarray, sample_rate: int) -> Signal:
    """Time vs amplitude, peak-preserving (min/max envelope) downsampled for the plot."""
    n = samples.size
    if n > _PLOT_POINTS * 2:
        step = n // _PLOT_POINTS
        block = samples[: step * _PLOT_POINTS].reshape(_PLOT_POINTS, step)
        times = np.repeat(np.arange(_PLOT_POINTS) * step / sample_rate, 2)
        amps = np.empty(_PLOT_POINTS * 2)
        amps[0::2], amps[1::2] = block.min(axis=1), block.max(axis=1)
    else:
        times, amps = np.arange(n) / sample_rate, samples
    return Signal(
        name="waveform", segment="Waveform",
        x=Axis(label="Time", unit="s", quantity="time"),
        y=Axis(label="Amplitude", unit=None, quantity="amplitude"),
        frame=pd.DataFrame({"Time": times, "Amplitude": amps}),
    )


def _fft_signal(samples: np.ndarray, sample_rate: int) -> Signal:
    """Frequency vs magnitude (dB, normalized to the peak), decimated for the plot."""
    windowed = samples * np.hanning(samples.size)
    mag = np.abs(np.fft.rfft(windowed))
    freq = np.fft.rfftfreq(samples.size, 1.0 / sample_rate)
    ref = mag.max() or 1.0
    db = 20.0 * np.log10(np.maximum(mag, ref * 1e-6) / ref)
    if freq.size > _PLOT_POINTS:
        step = freq.size // _PLOT_POINTS
        freq = freq[: step * _PLOT_POINTS].reshape(_PLOT_POINTS, step).mean(axis=1)
        db = db[: step * _PLOT_POINTS].reshape(_PLOT_POINTS, step).max(axis=1)  # keep peaks
    return Signal(
        name="fft", segment="Spectrum (FFT)",
        x=Axis(label="Frequency", unit="Hz", quantity="frequency"),
        y=Axis(label="Magnitude", unit="dB", quantity="magnitude"),
        frame=pd.DataFrame({"Frequency": freq, "Magnitude": db}),
    )
