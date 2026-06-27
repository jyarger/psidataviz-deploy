"""Reader for Bruker TopSpin **totxt** 2D ASCII exports (pseudo-2D / relaxation series).

The ``#`` comment header gives ``NROWS`` (indirect F1 dimension) × ``NCOLS`` (F2 = chemical shift)
plus the ``F2LEFT``/``F2RIGHT`` ppm limits; the body is NROWS blocks (each prefixed ``# row = N``)
of NCOLS intensities. Emitted as a **multi-signal** Dataset — one 1D ppm spectrum per F1 row — which
fits the existing model without a 2D extension (a true 2D heatmap view is future work).
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..model import Axis, Dataset, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate
from .nmr_jcamp import NMRMetadata

_INT = re.compile(r"=\s*(\d+)")
_FLOAT = r"=\s*(-?\d+\.?\d*(?:[eE][-+]?\d+)?)"
_NUCLEUS_RE = re.compile(r"(?:^|[_\-])(\d+[A-Z][a-z]?)(?:[_\-]|$)")


@register_reader
class NmrTotxtReader(BaseReader):
    technique = "NMR"
    name = "nmr_totxt"
    version = "0.1.0"
    extensions = (".txt",)

    def sniff(self, candidate: Candidate) -> float:
        head = candidate.head(4096)
        return 0.9 if ("# NROWS" in head and "# NCOLS" in head) else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        lines = candidate.as_text().splitlines()
        header = _parse_header(lines)
        ncols = header["ncols"]
        ppm_full = np.linspace(header["f2left"], header["f2right"], ncols)

        signals: list[Signal] = []
        row_values: list[float] = []
        row_index = 0

        def flush(values: list[float], idx: int) -> None:
            if not values:
                return
            n = min(len(values), ncols)
            signals.append(Signal(
                name=f"row {idx}", segment=f"F1 row {idx}",
                x=Axis(label="Chemical shift", unit="ppm", quantity="chemical_shift"),
                y=Axis(label="Intensity", unit="a.u.", quantity="intensity"),
                frame=pd.DataFrame({"Chemical shift": ppm_full[:n], "Intensity": values[:n]}),
            ))

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# row"):
                flush(row_values, row_index)
                row_values, row_index = [], row_index + 1
                continue
            if not stripped or stripped.startswith("#"):
                continue
            try:
                row_values.append(float(stripped))
            except ValueError:
                continue
        flush(row_values, row_index)

        if not signals:
            raise ValueError(f"No totxt rows decoded in {candidate.filename!r}")

        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version,
                              raw_header="\n".join(line for line in lines[:30]
                                                   if line.startswith("#"))),
            metadata=NMRMetadata(
                sample_name=candidate.stem, npoints=ncols,
                nucleus=(lambda m: m.group(1) if m else None)(_NUCLEUS_RE.search(candidate.stem)),
                extra={"n_rows": len(signals), "n_cols": ncols,
                       "f1_range": [header.get("f1left"), header.get("f1right")]},
            ),
            signals=signals,
        )


def _parse_header(lines: list[str]) -> dict:
    header: dict = {}
    for line in lines:
        if not line.startswith("#"):
            if "nrows" in header and "ncols" in header:
                break
            continue
        if "NROWS" in line and (m := _INT.search(line.split("NROWS", 1)[1])):
            header["nrows"] = int(m.group(1))
        if "NCOLS" in line and (m := _INT.search(line.split("NCOLS", 1)[1])):
            header["ncols"] = int(m.group(1))
        for key, token in (("f2left", "F2LEFT"), ("f2right", "F2RIGHT"),
                           ("f1left", "F1LEFT"), ("f1right", "F1RIGHT")):
            if token in line and (m := re.search(_FLOAT, line.split(token, 1)[1])):
                header[key] = float(m.group(1))
    if "nrows" not in header or "ncols" not in header:
        raise ValueError("totxt header missing NROWS/NCOLS")
    header.setdefault("f2left", float(header["ncols"] - 1))
    header.setdefault("f2right", 0.0)
    return header
