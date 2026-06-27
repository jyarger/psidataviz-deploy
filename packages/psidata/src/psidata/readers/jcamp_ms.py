"""Reader for **mass spectra** in JCAMP-DX — e.g. ChemSpectra/Chemotion exports.

The data is ``##DATA TYPE=MASS SPECTRUM`` with ``##DATA CLASS=NTUPLES``: one or more ``##PAGE`` blocks,
each a ``##DATA TABLE= (XY..XY), PEAKS`` of ``(m/z, relative abundance)`` peak pairs. All pages are merged
into a single mass spectrum (peaks sorted by m/z), shown on an m/z axis.
"""

from __future__ import annotations

import re

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate

_LDR_RE = re.compile(r"^##\$?([^=]+)=(.*)$")


_MS_TECHNIQUES = {"MASS SPEC", "SIMS"}  # standard MS vs secondary-ion MS (same JCAMP, different hint)


class _JcampMassSpecReader(BaseReader):
    """Shared JCAMP mass-spectrum parsing; concrete subclasses bind the technique (MS vs SIMS)."""

    version = "0.1.0"
    extensions = (".jdx", ".dx")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        head = candidate.head(4096).upper()
        if "##JCAMP-DX" not in head:
            return 0.0
        if "MASS SPECTRUM" in head:
            return 0.92
        hint = (candidate.technique_hint or "").upper()
        if hint.startswith("MASS") or hint == "SIMS":
            return 0.6
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        lines = candidate.as_text().splitlines()
        title = None
        peaks: list[tuple[float, float]] = []
        pages = 0
        in_data = False
        for raw in lines:
            stripped = raw.strip()
            if stripped.lstrip().startswith("##"):  # a labeled record, not data
                in_data = False
                m = _LDR_RE.match(stripped)
                if m:
                    label = m.group(1).strip().upper().replace(" ", "")
                    if label == "TITLE" and title is None:
                        title = m.group(2).split("$$")[0].strip()
                    elif label == "PAGE":
                        pages += 1
                    elif label.startswith("DATATABLE"):
                        in_data = True
                continue
            if in_data and stripped:
                nums = []
                for token in stripped.split("##")[0].replace(",", " ").split():
                    try:
                        nums.append(float(token))
                    except ValueError:
                        break  # stop at the first non-number (e.g. a trailing ##END fragment)
                for i in range(0, len(nums) - 1, 2):
                    peaks.append((nums[i], nums[i + 1]))
        if not peaks:
            raise ValueError(f"{candidate.filename}: no mass-spectrum peaks found")
        peaks.sort(key=lambda p: p[0])
        frame = pd.DataFrame(peaks, columns=["m/z", "Relative abundance"])
        signal = Signal(
            name="mass spectrum",
            x=Axis(label="m/z", unit=None, quantity="mass_to_charge"),
            y=Axis(label="Relative abundance", unit="a.u.", quantity="intensity"),
            frame=frame,
        )
        # MS and SIMS share this JCAMP format; honour the folder/filename hint so each is labelled right
        hint = candidate.technique_hint
        technique = hint if (hint or "").upper() in _MS_TECHNIQUES else self.technique
        return Dataset(
            technique=technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version),
            metadata=Metadata(sample_name=title or candidate.stem,
                              notes=f"{pages} scan page(s) merged" if pages > 1 else None),
            signals=[signal],
        )


@register_reader
class JcampMassSpecReader(_JcampMassSpecReader):
    technique = "Mass Spec"
    name = "jcamp_ms"


@register_reader
class JcampSimsReader(_JcampMassSpecReader):
    technique = "SIMS"
    name = "jcamp_sims"
