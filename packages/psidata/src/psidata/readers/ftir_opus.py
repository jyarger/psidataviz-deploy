"""Reader for **Bruker OPUS** FTIR files — the numeric-extension binaries (``name.0``, ``name.1``, …).

Bruker OPUS software (Alpha / Vertex / Tensor) saves raw FTIR data in a proprietary binary with a
numeric extension and the magic bytes ``0x0A0A FEFE``. Parsed via
[`brukeropusreader`](https://github.com/qedsoftware/brukeropusreader) (the ``[convert]`` extra); the
absorbance (``AB``) block — or transmittance / single-channel — becomes an FTIR spectrum on a
wavenumber axis. Sample/instrument come from the OPUS parameter blocks.
"""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate

_OPUS_MAGIC = b"\n\n\xfe\xfe"


@register_reader
class FtirOpusReader(BaseReader):
    technique = "FTIR"
    name = "ftir_opus"
    version = "0.1.0"
    extensions = tuple(f".{i}" for i in range(10))  # OPUS .0 .. .9

    def sniff(self, candidate: Candidate) -> float:
        if candidate.ext not in self.extensions:
            return 0.0
        return 0.95 if (candidate.content or b"")[:4] == _OPUS_MAGIC else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        try:
            from brukeropusreader import read_file
        except ImportError as exc:
            raise ImportError("reading Bruker OPUS files needs brukeropusreader: "
                              "pip install 'psidata[convert]'") from exc
        fd, tmp = tempfile.mkstemp(suffix=candidate.ext)
        try:
            os.write(fd, candidate.content or b"")
            os.close(fd)
            od = read_file(tmp)
        finally:
            os.unlink(tmp)

        block, y_label, y_quantity = _pick_block(od)
        x = np.asarray(od.get_range(block), dtype=float)
        y = np.asarray(od[block], dtype=float)[: len(x)]
        signal = Signal(
            name="spectrum",
            x=Axis(label="Wavenumber", unit="cm⁻¹", quantity="wavenumber"),
            y=Axis(label=y_label, unit="a.u.", quantity=y_quantity),
            frame=pd.DataFrame({"Wavenumber": x, y_label: y}),
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=Metadata(sample_name=_param(od, "Sample", "SNM") or candidate.stem,
                              instrument=_param(od, "Instrument", "INS") or "Bruker OPUS"),
            signals=[signal],
        )


def _pick_block(od) -> tuple[str, str, str]:
    if "AB" in od:
        return "AB", "Absorbance", "absorbance"
    if "TR" in od:
        return "TR", "Transmittance", "transmittance"
    if "ScSm" in od:
        return "ScSm", "Intensity", "intensity"
    raise ValueError("no FTIR data block (AB / TR / ScSm) found in OPUS file")


def _param(od, block: str, key: str) -> str | None:
    b = od.get(block)
    if isinstance(b, dict) and b.get(key):
        return str(b[key]).strip() or None
    return None
