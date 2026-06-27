"""Reader for **Brillouin** spectra exported from a multichannel scaler (``.asc``).

Tandem Fabry–Pérot Brillouin setups record the interferometer scan on an MCS card; the ASCII export
(EG&G/Ortec-style) has a ``KEY = value`` header (``DWELL TIME``, ``PASS LENGTH``, ``PASS COUNT``,
``CALIBRATION UNITS``, …) followed by ``CH <start-channel> <count> <count> …`` rows. We reassemble the
per-channel intensity into one spectrum (intensity vs channel).
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate


class BrillouinMetadata(Metadata):
    dwell_time_us: float | None = None
    pass_length: int | None = None
    pass_count: int | None = None
    calibration_units: str | None = None


@register_reader
class BrillouinAscReader(BaseReader):
    technique = "Brillouin"
    name = "brillouin_asc"
    version = "0.1.0"
    extensions = (".asc",)

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext != ".asc":
            return 0.0
        head = candidate.head(2000).upper()
        # MCS-specific markers distinguish this from FTIR/XRD ".asc" exports
        if "PASS LENGTH" in head or "PASS COUNT" in head or ("DWELL TIME" in head and "\nCH" in head):
            return 0.9
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        header: dict[str, str] = {}
        counts: dict[int, int] = {}
        for line in candidate.as_text().splitlines():
            stripped = line.strip()
            if stripped[:2].upper() == "CH":
                nums = _leading_ints(stripped.split()[1:])
                if len(nums) >= 2:  # first is the starting channel, rest are intensities
                    for offset, value in enumerate(nums[1:]):
                        counts[nums[0] + offset] = value
            elif "=" in line:
                key, _, value = line.partition("=")
                header[key.strip().upper()] = value.strip()
        if not counts:
            raise ValueError(f"{candidate.filename}: no 'CH' data rows found")

        channels = sorted(counts)
        frame = pd.DataFrame({"Channel": channels, "Intensity": [counts[c] for c in channels]})
        signal = Signal(
            name="spectrum",
            x=Axis(label="Channel", unit=None, quantity="channel"),
            y=Axis(label="Intensity", unit="counts", quantity="intensity"),
            frame=frame,
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=_metadata(header, candidate.stem),
            signals=[signal],
        )


def _leading_ints(tokens: list[str]) -> list[int]:
    out: list[int] = []
    for tok in tokens:
        try:
            out.append(int(tok))
        except ValueError:
            break
    return out


def _metadata(header: dict[str, str], stem: str) -> BrillouinMetadata:
    return BrillouinMetadata(
        sample_name=stem,
        instrument="Brillouin (MCS)",
        date=_parse_date(header.get("START DATE")),
        dwell_time_us=_num(header.get("DWELL TIME")),
        pass_length=_int(header.get("PASS LENGTH")),
        pass_count=_int(header.get("PASS COUNT")),
        calibration_units=header.get("CALIBRATION UNITS") or None,
    )


def _num(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.split()[0])
    except (ValueError, IndexError):
        return None


def _int(value: str | None) -> int | None:
    n = _num(value)
    return int(n) if n is not None else None


def _parse_date(value: str | None):
    if not value:
        return None
    for fmt in ("%m-%d-%y", "%m-%d-%Y", "%d-%b-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None
