"""Reader for **2D (nD) NMR** spectra in JCAMP-DX ``NTUPLES`` form — Bruker/MestReNova exports of
COSY, HSQC, HMBC, NOESY, TOCSY, … (``.jdx``/``.dx``).

The data is stored one **F1 increment per page**, each page an ASDF ``(F2++(Y..Y))`` profile across the
direct (F2) dimension. We assemble the pages into an intensity matrix and expose it as a 2D *map* with
real chemical-shift (ppm) axes, so the app can render it as a contour. The shared 1D ASDF decoder
(:func:`._asdf.decode_xpp_yy`) decodes each row.
"""

from __future__ import annotations

import re

import numpy as np

from ..model import Axis, Dataset, Image2D, SourceInfo
from ..registry import register_reader
from ._asdf import decode_xpp_yy
from .base import BaseReader, Candidate
from .nmr_jcamp import NMRMetadata

_F1_RE = re.compile(r"F1\s*=\s*([-\d.eE]+)")


def _attr(lines: list[str], key: str, *, prefer_multi: bool = False) -> str | None:
    """Value of an LDR (``##KEY=``). With ``prefer_multi`` return the comma-list occurrence — a 2D
    NTUPLES file repeats e.g. ``.OBSERVE FREQUENCY`` as both a scalar and a per-dimension list."""
    hits = []
    for line in lines:
        flat = line.replace("\t", " ")
        if flat.lstrip().upper().startswith("##" + key.upper() + "="):
            hits.append(flat.split("=", 1)[1].strip())
    if not hits:
        return None
    if prefer_multi:
        return next((h for h in hits if "," in h), hits[0])
    return hits[0]


def _floats(value: str | None) -> list[float]:
    out = []
    for tok in (value or "").split(","):
        try:
            out.append(float(tok.strip()))
        except ValueError:
            pass
    return out


@register_reader
class Nmr2DJcampReader(BaseReader):
    technique = "NMR"
    name = "nmr_2d_jcamp"
    version = "0.1.0"
    extensions = (".jdx", ".dx", ".jcamp")

    def sniff(self, candidate: Candidate) -> float:
        head = candidate.head(8192).upper()
        if "##JCAMP-DX" not in head or "NTUPLES" not in head:
            return 0.0
        two_d = "ND NMR SPECTRUM" in head or re.search(r"NUMDIM=\s*[2-9]", head)
        return 0.95 if two_d else 0.0

    def read(self, candidate: Candidate) -> Dataset:
        lines = candidate.as_text().splitlines()
        dims = [int(v) for v in _floats(_attr(lines, "VAR_DIM", prefer_multi=True))]
        first = _floats(_attr(lines, "FIRST", prefer_multi=True))
        last = _floats(_attr(lines, "LAST", prefer_multi=True))
        factor = _floats(_attr(lines, "FACTOR", prefer_multi=True))
        obs = _floats(_attr(lines, ".OBSERVE FREQUENCY", prefer_multi=True))
        units = [u.strip() for u in (_attr(lines, "UNITS", prefer_multi=True) or "").split(",")]
        nuclei = [n.strip().lstrip("^") for n in (_attr(lines, ".NUCLEUS", prefer_multi=True) or "").split(",")]
        if len(dims) < 2 or len(first) < 2 or len(last) < 2:
            raise ValueError("nmr_2d_jcamp: incomplete NTUPLES axis metadata for a 2D spectrum")

        n_f2 = dims[1]
        y_factor = factor[2] if len(factor) > 2 else 1.0
        rows, f1_hz = self._decode_pages(lines, n_f2, y_factor)
        if not rows:
            raise ValueError("nmr_2d_jcamp: no decodable NTUPLES pages")
        z = np.vstack(rows)

        # F2 indexes the columns (direct dimension), F1 the rows (indirect dimension)
        sf_f1 = obs[0] if obs else None
        sf_f2 = obs[1] if len(obs) > 1 else None
        x_values = np.linspace(first[1], last[1], n_f2) / (sf_f2 or 1.0)
        y_values = np.asarray(f1_hz, dtype=float) / (sf_f1 or 1.0)
        x_unit = "ppm" if sf_f2 else (units[1] if len(units) > 1 else None)
        y_unit = "ppm" if sf_f1 else (units[0] if len(units) > 0 else None)
        f2_nuc = nuclei[1] if len(nuclei) > 1 else ""
        f1_nuc = nuclei[0] if len(nuclei) > 0 else ""

        image = Image2D(
            name=candidate.stem,
            data=z,
            x=Axis(label=f"{f2_nuc} F2".strip(), unit=x_unit, quantity="chemical_shift"),
            y=Axis(label=f"{f1_nuc} F1".strip(), unit=y_unit, quantity="chemical_shift"),
            z=Axis(label="Intensity", unit="a.u.", quantity="intensity"),
            kind="nmr2d",
            x_values=x_values,
            y_values=y_values,
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version,
                              raw_header="\n".join(lines[:60])),
            metadata=self._metadata(lines, candidate, z.shape, f1_nuc, f2_nuc, sf_f2),
            images=[image],
        )

    def _decode_pages(self, lines: list[str], n_f2: int,
                      y_factor: float) -> tuple[list[np.ndarray], list[float]]:
        starts = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("##PAGE")]
        starts.append(len(lines))
        rows: list[np.ndarray] = []
        f1_hz: list[float] = []
        for k in range(len(starts) - 1):
            block = lines[starts[k]:starts[k + 1]]
            m = _F1_RE.search(block[0])
            table = next((j for j, ln in enumerate(block) if "DATA TABLE" in ln.upper()), None)
            if m is None or table is None:
                continue
            _x0, _direction, ordinates = decode_xpp_yy(block[table + 1:], npoints=n_f2)
            if not ordinates:
                continue
            row = np.asarray(ordinates, dtype=float) * y_factor
            if row.size < n_f2:
                row = np.pad(row, (0, n_f2 - row.size))
            rows.append(row[:n_f2])
            f1_hz.append(float(m.group(1)))
        return rows, f1_hz

    def _metadata(self, lines, candidate, shape, f1_nuc, f2_nuc, sf_f2) -> NMRMetadata:
        data_types = [ln.replace("\t", " ").split("=", 1)[1].strip()
                      for ln in lines if ln.replace("\t", " ").lstrip().upper().startswith("##DATA TYPE=")]
        nmr_type = next((dt for dt in data_types if "NMR" in dt.upper()), None)
        meta = NMRMetadata(
            sample_name=_attr(lines, "TITLE") or candidate.stem,
            instrument=_attr(lines, "ORIGIN"),
            nucleus=f2_nuc or None,
            frequency_mhz=sf_f2,
            solvent=_attr(lines, ".SOLVENT NAME") or _attr(lines, ".SOLVENT"),
            pulse_sequence=_attr(lines, ".PULSE SEQUENCE"),
            data_type=nmr_type,
        )
        meta.experiment = f"{f1_nuc}-{f2_nuc} 2D" if (f1_nuc and f2_nuc) else "2D NMR"
        meta.dimensions = f"{shape[0]} × {shape[1]}"
        return meta
