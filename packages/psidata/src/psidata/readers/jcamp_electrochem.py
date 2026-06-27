"""Reader for **electrochemistry** data in JCAMP-DX — e.g. **Chemotion** converter exports.

The Chemotion converter app packages a measurement as a BagIt zip whose ``data/`` holds JCAMP-DX
``.jdx`` tables with ``##DATA TYPE=CYCLIC VOLTAMMETRY`` (or another voltammetry/amperometry type) and
explicit ``##XUNITS=Voltage in V`` / ``##YUNITS=Current in A``. JCAMP parsing is shared with the NMR/FTIR
readers (:mod:`._jcamp`); this reader claims the electrochemistry data types and takes its axes from the
declared units, so a cyclic voltammogram reads as Potential (V) vs Current (A) rather than an NMR spectrum.
"""

from __future__ import annotations

import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from ._jcamp import decode_data, header_index, parse_ldrs_and_data
from .base import BaseReader, Candidate

# ``##DATA TYPE`` values that mean electrochemistry (matched as substrings of the upper-cased header).
ECHEM_DATA_TYPES = (
    "VOLTAMMETRY", "AMPEROMETRY", "POTENTIOMETRY", "VOLTAMMOGRAM", "CHRONOAMPEROMETRY",
    "CHRONOPOTENTIOMETRY", "ELECTROCHEMICAL IMPEDANCE",
)


@register_reader
class JcampElectrochemReader(BaseReader):
    technique = "Electrochem"
    name = "jcamp_electrochem"
    version = "0.1.0"
    extensions = (".jdx", ".dx")

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        head = candidate.head(4096).upper()
        if "##JCAMP-DX" not in head:
            return 0.0
        if any(t in head for t in ECHEM_DATA_TYPES):
            return 0.92  # the file declares itself electrochemistry
        if (candidate.technique_hint or "").upper().startswith("ELECTROCHEM"):
            return 0.6
        return 0.0

    def read(self, candidate: Candidate) -> Dataset:
        lines = candidate.as_text().splitlines()
        ldrs, marker, data_lines = parse_ldrs_and_data(lines)
        x, y = decode_data(ldrs, marker, data_lines)
        x_label, x_unit = _axis(ldrs.get("XUNITS"), "Potential", "V")
        y_label, y_unit = _axis(ldrs.get("YUNITS"), "Current", "A")
        signal = Signal(
            name=(ldrs.get("DATATYPE") or "voltammogram").title(),
            x=Axis(label=x_label, unit=x_unit, quantity="potential"),
            y=Axis(label=y_label, unit=y_unit, quantity="current"),
            frame=pd.DataFrame({x_label: x, y_label: y}),
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename, reader=self.name,
                              reader_version=self.version,
                              raw_header="\n".join(lines[: header_index(lines)])),
            metadata=Metadata(
                sample_name=ldrs.get("TITLE") or candidate.stem,
                instrument=ldrs.get("SERIAL") or ldrs.get("INSTRUMENT"),
                date=_parse_date(ldrs.get("DATE")),
            ),
            signals=[signal],
        )


def _axis(units: str | None, default_label: str, default_unit: str) -> tuple[str, str]:
    """Read a JCAMP units string like ``"Voltage in V"`` into a (label, unit) pair."""
    if units and " in " in units:
        quantity, unit = units.split(" in ", 1)
        unit = unit.strip()
        label = {"v": "Potential", "a": "Current"}.get(unit.lower(), quantity.strip() or default_label)
        return label, unit
    return default_label, default_unit


def _parse_date(value: str | None):
    from datetime import datetime
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%m.%d.%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None
