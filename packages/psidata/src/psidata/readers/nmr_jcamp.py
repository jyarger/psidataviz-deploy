"""Reader for **NMR** spectra in JCAMP-DX (``.jdx``, ``.dx``, and Agilent/Varian ``.txt``).

Shared JCAMP parsing lives in :mod:`._jcamp`; this reader adds NMR-specific detection (it declines
INFRARED/RAMAN/UV JCAMP, which the FTIR reader handles), axes, and metadata. Both plain ``(XY..XY)``
and ASDF-compressed ``(X++(Y..Y))`` data are supported. Abscissa is reported in the file's
``XUNITS`` (Hz for many Bruker exports, ppm for others); absolute Hz→ppm referencing is future work.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from ._asdf import decode_xpp_yy
from ._jcamp import (
    decode_data,
    header_index,
    is_ntuples_fid,
    ldr_float,
    ntuples_attr,
    parse_ldrs_and_data,
    parse_ntuples_pages,
)
from .base import BaseReader, Candidate

_NON_NMR = ("INFRARED", "RAMAN", "UV/VIS", "UV-VIS", "UVVIS", "MASS SPECTRUM",
            "VOLTAMMETRY", "VOLTAMMOGRAM", "AMPEROMETRY", "POTENTIOMETRY")


class NMRMetadata(Metadata):
    """NMR-specific metadata layered on the common fields."""

    nucleus: str | None = None
    frequency_mhz: float | None = None
    solvent: str | None = None
    pulse_sequence: str | None = None
    temperature_k: float | None = None
    data_type: str | None = None
    npoints: int | None = None


@register_reader
class JcampNmrReader(BaseReader):
    technique = "NMR"
    name = "nmr_jcamp"
    version = "0.3.0"
    extensions = (".jdx", ".dx", ".txt")

    def sniff(self, candidate: Candidate) -> float:
        head = candidate.head(4096).upper()
        if "##JCAMP-DX" not in head:
            return 0.0
        if any(marker in head for marker in _NON_NMR):
            return 0.0  # belongs to FTIR / another technique's JCAMP reader
        if "ND NMR SPECTRUM" in head or re.search(r"NUMDIM=\s*[2-9]", head):
            return 0.0  # a 2D/nD NMR spectrum — nmr_2d_jcamp handles it
        # NTUPLES (multi-page) JCAMP: we decode the NMR-FID variant; decline others so the catalog
        # doesn't mark an undecodable NTUPLES class as "supported".
        if "DATA CLASS=NTUPLES" in head and "FID" not in head:
            return 0.0
        score = 0.1 if candidate.ext in self.extensions else 0.0
        score += 0.5
        if "NMR SPECTRUM" in head or "NMR FID" in head \
                or "OBSERVE NUCLEUS" in head or "OBSERVE FREQUENCY" in head:
            score += 0.35
        elif (candidate.technique_hint or "").upper() == "NMR":
            score += 0.2
        return min(score, 1.0)

    def read(self, candidate: Candidate) -> Dataset:
        lines = candidate.as_text().splitlines()
        ldrs, marker, data_lines = parse_ldrs_and_data(lines)
        if is_ntuples_fid(ldrs):
            return self._read_ntuples_fid(lines, ldrs, candidate)
        x, y = decode_data(ldrs, marker, data_lines)

        x_unit = (ldrs.get("XUNITS") or "ppm").strip().lower()
        x_label, x_unit_disp = ("Frequency", "Hz") if x_unit in ("hz", "hertz") \
            else ("Chemical shift", "ppm")
        frame = pd.DataFrame({x_label: x, "Intensity": y})

        signal = Signal(
            name="spectrum",
            x=Axis(label=x_label, unit=x_unit_disp, quantity="chemical_shift"),
            y=Axis(label="Intensity", unit="a.u.", quantity="intensity"),
            frame=frame,
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version,
                              raw_header="\n".join(lines[: header_index(lines)])),
            metadata=_build_metadata(ldrs, candidate, npoints=len(frame)),
            signals=[signal],
        )

    def _read_ntuples_fid(self, lines: list[str], ldrs: dict[str, str],
                          candidate: Candidate) -> Dataset:
        """Decode an NTUPLES NMR FID (REAL/IMAG pages) and FT it to a magnitude spectrum.

        The stored data is a *time-domain* FID, so it is Fourier-transformed onto the chemical-shift
        (ppm) axis. We return a **magnitude** spectrum (phase-robust quick-look) — the FID is
        exponentially apodized (``LB``), zero-filled to ``SI`` and FFT'd; unlike full NMR processing
        it is not phase- or baseline-corrected.
        """
        pages = parse_ntuples_pages(lines)
        factor = dict(zip(ntuples_attr(ldrs, "SYMBOL"), ntuples_attr(ldrs, "FACTOR"), strict=False))
        np_str = ldr_float(ldrs, "NPOINTS")
        npoints = int(np_str) if np_str else None

        def page(sym: str) -> np.ndarray | None:
            raw = pages.get(sym)
            if not raw:
                return None
            _x0, _direction, ordinates = decode_xpp_yy(raw, npoints=npoints)
            if not ordinates:
                return None
            return np.asarray(ordinates, dtype=float) * float(factor.get(sym) or 1.0)

        real = page("R")
        if real is None:
            raise ValueError("NTUPLES FID has no decodable REAL page")
        ppm, intensity = _fid_to_spectrum(real, page("I"), ldrs)

        signal = Signal(
            name="spectrum",
            x=Axis(label="Chemical shift", unit="ppm", quantity="chemical_shift"),
            y=Axis(label="Intensity", unit="a.u.", quantity="intensity"),
            frame=pd.DataFrame({"Chemical shift": ppm, "Intensity": intensity}),
        )
        meta = _build_metadata(ldrs, candidate, npoints=len(real))
        meta.data_type = "NMR FID → magnitude spectrum (FFT)"
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version,
                              raw_header="\n".join(lines[: header_index(lines)])),
            metadata=meta,
            signals=[signal],
        )


def _fid_to_spectrum(real: np.ndarray, imag: np.ndarray | None,
                     ldrs: dict[str, str]) -> tuple[np.ndarray, np.ndarray]:
    """FT a complex FID to a magnitude spectrum on a ppm axis, from the acquisition LDRs.

    The imaginary channel is conjugated (``R - iI``) to match the NMReady/Bruker quadrature sign so
    peaks land at the correct chemical shift; the ppm axis runs from ``OFFSET`` (left/high) downward.
    """
    sf = (ldr_float(ldrs, "SF") or ldr_float(ldrs, "BF1") or ldr_float(ldrs, "SFO1")
          or ldr_float(ldrs, ".OBSERVEFREQUENCY"))
    swh = ldr_float(ldrs, "SWH")
    deltax = ldr_float(ldrs, "DELTAX")  # time step per point (s)
    if not swh and deltax:
        swh = 1.0 / deltax
    sw_ppm = (swh / sf) if (swh and sf) else ldr_float(ldrs, "SW")
    offset = ldr_float(ldrs, "OFFSET")
    o1p = ldr_float(ldrs, "O1P")
    if offset is None and o1p is not None and sw_ppm:
        offset = o1p + sw_ppm / 2.0
    lb = ldr_float(ldrs, "LB") or 0.0
    si = int(ldr_float(ldrs, "SI") or 0)

    if imag is not None and len(imag) == len(real):
        fid = real - 1j * imag
    else:
        fid = real.astype(complex)
    n = len(fid)
    if swh and lb:
        fid = fid * np.exp(-np.pi * lb * np.arange(n) / swh)
    si = max(si, n)
    fid = np.concatenate([fid, np.zeros(si - n)])
    mag = np.abs(np.fft.fftshift(np.fft.fft(fid)))
    if offset is not None and sw_ppm:
        ppm = offset - np.arange(si) * sw_ppm / si
    else:
        ppm = np.arange(si)[::-1].astype(float)
    return ppm, mag


def _build_metadata(ldrs: dict[str, str], candidate: Candidate, npoints: int) -> NMRMetadata:
    return NMRMetadata(
        sample_name=ldrs.get("TITLE") or candidate.stem,
        instrument=ldrs.get("SPECTROMETER/DATASYSTEM") or ldrs.get("ORIGIN"),
        nucleus=_clean_nucleus(ldrs.get(".OBSERVENUCLEUS")),
        frequency_mhz=ldr_float(ldrs, ".OBSERVEFREQUENCY"),
        solvent=ldrs.get(".SOLVENT") or ldrs.get(".SOLVENTNAME") or ldrs.get("SOLVENT"),
        pulse_sequence=ldrs.get("PULSESEQUENCE"),
        temperature_k=ldr_float(ldrs, "TEMPERATURE"),
        data_type=ldrs.get("DATATYPE"),
        npoints=npoints,
    )


def _clean_nucleus(value: str | None) -> str | None:
    return value.replace("^", "").strip() if value else None
