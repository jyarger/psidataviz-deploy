"""Reader for **UV-Vis** spectra in text form.

Handles bare ``wavelength, value`` tables (``.txt``/``.csv``) and the Thorlabs CCS-series ``.csv`` export,
which carries a ``#key,value`` header block (``#XAxisUnit``, ``#YAxisUnit``, instrument, integration time)
followed by the data. The y quantity (intensity / absorbance / transmittance) is taken from the header
when present. Vendor binary ``.spf2`` files are not handled. Like Raman, bare tables are
content-ambiguous, so detection leans on the source folder hinting "UV-Vis".
"""

from __future__ import annotations

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from ._tabular import parse_numeric_table
from .base import BaseReader, Candidate

_UV_HINTS = {"UV-VIS", "UVVIS", "UV", "UV-VISIBLE", "UV_VIS"}
_UV_CUES = ("thorlabs", "spectrumheader", "ccs1", "ccs2", "xaxisunit")


class UVVisMetadata(Metadata):
    """UV-Vis-specific metadata layered on the common fields."""

    measurement_type: str | None = None  # emission / absorption / transmission
    integration_time_ms: float | None = None
    npoints: int | None = None


@register_reader
class UVVisTextReader(BaseReader):
    technique = "UV-Vis"
    name = "uvvis_text"
    version = "0.1.0"
    extensions = (".csv", ".txt")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        low = candidate.head(4096).lower()
        hint = (candidate.technique_hint or "").upper().replace(" ", "")
        score = 0.6 if hint in _UV_HINTS else 0.0
        if any(cue in low for cue in _UV_CUES):
            score += 0.4
        if score == 0.0:
            return 0.0
        return min(score, 1.0) if not parse_numeric_table(candidate.head(8192)).empty else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        text = candidate.as_text()
        table = parse_numeric_table(text)
        if table.empty or table.shape[1] < 2:
            raise ValueError(f"No UV-Vis spectrum (wavelength, value) found in {candidate.filename!r}")
        header = _hash_header(text)
        y_label, y_quantity = _y_axis(header.get("yaxisunit", ""))
        wavelength = table["col0"].rename("Wavelength")
        value = table["col1"].rename(y_label)
        signal = Signal(
            name="spectrum",
            x=Axis(label="Wavelength", unit="nm", quantity="wavelength"),
            y=Axis(label=y_label, unit="a.u.", quantity=y_quantity),
            frame=wavelength.to_frame().join(value),
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=UVVisMetadata(
                sample_name=candidate.stem,
                instrument=header.get("instrmodel") or header.get("instrument"),
                measurement_type=header.get("type"),
                integration_time_ms=_as_float(header.get("integrationtime")),
                npoints=len(wavelength),
            ),
            signals=[signal],
        )


def _hash_header(text: str) -> dict[str, str]:
    """Parse ``#Key,Value`` (and ``Key,Value``) header lines into a lowercased-key dict."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("#") or "," not in s:
            continue
        key, _, value = s.lstrip("#").partition(",")
        key = key.strip().lower()
        if key and value.strip():
            out.setdefault(key, value.strip())
    return out


def _y_axis(unit: str) -> tuple[str, str]:
    u = unit.lower()
    if "absorb" in u:
        return "Absorbance", "absorbance"
    if "transmit" in u or "%t" in u:
        return "Transmittance", "transmittance"
    return "Intensity", "intensity"


def _as_float(s: str | None) -> float | None:
    try:
        return float(s) if s is not None else None
    except ValueError:
        return None
