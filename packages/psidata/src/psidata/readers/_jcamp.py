"""Shared, technique-agnostic JCAMP-DX parsing (used by the NMR and FTIR readers).

JCAMP-DX is a labeled-text standard: ``##LABEL= value`` header records (LDRs) followed by a data
section. This module parses the LDRs and reconstructs ``(x, y)`` from both encodings:

* plain ``(XY..XY)`` pairs (x carried per point), and
* ASDF-compressed ``(X++(Y..Y))`` (decoded via :mod:`._asdf`).

The x grid for the compressed form is rebuilt from ``FIRSTX``/``LASTX``/``NPOINTS`` and the data
direction, so it is correct whether the stored abscissa is a point *index* (NMR Bruker, where
XFACTOR == ΔX) or the *actual* value (FTIR Nicolet, where XFACTOR == 1 and points are ΔX apart).
"""

from __future__ import annotations

import re

from ._asdf import decode_xpp_yy

_LDR_RE = re.compile(r"^##\$?([^=]+)=(.*)$")
XY_FORM = "(XY..XY)"
ASDF_FORM = "(X++(Y..Y))"


def parse_ldrs_and_data(lines: list[str]) -> tuple[dict[str, str], str | None, list[str]]:
    """Return ``(ldrs, data_marker, data_lines)``. LDR keys are upper-cased, spaces removed."""
    ldrs: dict[str, str] = {}
    data_marker: str | None = None
    data_lines: list[str] = []
    in_data = False
    for line in lines:
        if in_data:
            if line.startswith("##END"):
                break
            data_lines.append(line)
            continue
        m = _LDR_RE.match(line)
        if not m:
            continue
        label = m.group(1).strip().upper().replace(" ", "")
        value = m.group(2).split("$$")[0].strip()
        if label in ("XYDATA", "XYPOINTS", "PEAKTABLE"):
            data_marker = value
            in_data = True
            continue
        ldrs[label] = value
    return ldrs, data_marker, data_lines


def data_form(marker: str | None) -> str:
    return ASDF_FORM if "X++(Y..Y)" in (marker or "").replace(" ", "") else XY_FORM


def ldr_float(ldrs: dict[str, str], key: str, default: float | None = None) -> float | None:
    value = ldrs.get(key)
    if value in (None, ""):
        return default
    try:
        return float(value.split("$$")[0].split()[0])
    except (ValueError, IndexError):
        return default


def header_index(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if line.upper().startswith(("##XYDATA", "##XYPOINTS", "##PEAKTABLE", "##NTUPLES")):
            return i
    return len(lines)


# --- NTUPLES (multi-page) data, e.g. an NMR FID with separate REAL/IMAG pages ------------------
_NTUPLE_TABLE_RE = re.compile(r"\(X\+\+\(([A-Z])\.\.\1\)\)")


def is_ntuples_fid(ldrs: dict[str, str]) -> bool:
    """True for a JCAMP NTUPLES block holding a time-domain NMR FID (REAL/IMAG pages)."""
    return ldrs.get("DATACLASS", "").upper() == "NTUPLES" and "FID" in ldrs.get("DATATYPE", "").upper()


def ntuples_attr(ldrs: dict[str, str], key: str) -> list[str]:
    """Split a comma-list NTUPLES attribute (``SYMBOL``, ``FACTOR``, ``VAR_DIM``, …)."""
    return [s.strip() for s in (ldrs.get(key) or "").split(",")]


def parse_ntuples_pages(lines: list[str]) -> dict[str, list[str]]:
    """Map each NTUPLES page's ordinate symbol (``R``, ``I``, …) to its raw ``(X++(?..?))`` lines."""
    pages: dict[str, list[str]] = {}
    sym: str | None = None
    buf: list[str] = []
    for line in lines:
        compact = line.strip().replace(" ", "").upper()
        if compact.startswith("##DATATABLE"):
            if sym is not None:
                pages[sym] = buf
            m = _NTUPLE_TABLE_RE.search(compact)
            sym, buf = (m.group(1) if m else None), []
        elif line.lstrip().startswith("##"):
            if sym is not None:
                pages[sym] = buf
                sym, buf = None, []
        elif sym is not None:
            buf.append(line)
    if sym is not None:
        pages[sym] = buf
    return pages


def decode_data(ldrs: dict[str, str], marker: str | None,
                data_lines: list[str]) -> tuple[list[float], list[float]]:
    """Reconstruct (x, y) from a JCAMP data section, dispatching on the encoding."""
    xfactor = ldr_float(ldrs, "XFACTOR", 1.0)
    yfactor = ldr_float(ldrs, "YFACTOR", 1.0)
    if data_form(marker) == ASDF_FORM:
        return _decode_asdf(ldrs, data_lines, xfactor, yfactor)
    return _parse_xy_pairs(data_lines, xfactor, yfactor)


def _parse_xy_pairs(data_lines: list[str], xfactor: float,
                    yfactor: float) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for line in data_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("##", "$$")):
            continue
        nums = []
        for token in stripped.replace(",", " ").replace(";", " ").split():
            try:
                nums.append(float(token))
            except ValueError:
                continue
        for i in range(0, len(nums) - 1, 2):
            xs.append(nums[i] * xfactor)
            ys.append(nums[i + 1] * yfactor)
    return xs, ys


def _decode_asdf(ldrs: dict[str, str], data_lines: list[str], xfactor: float,
                 yfactor: float) -> tuple[list[float], list[float]]:
    """Decode ``(X++(Y..Y))`` ordinates; emit only if validated against the header, else raise."""
    npoints_str = ldrs.get("NPOINTS")
    npoints = int(float(npoints_str)) if npoints_str else None
    x0, direction, ordinates = decode_xpp_yy(data_lines, npoints=npoints)
    if x0 is None or not ordinates:
        raise ValueError("ASDF block contained no decodable ordinates")
    n = len(ordinates)
    firsty = ldr_float(ldrs, "FIRSTY")
    if firsty is not None:
        actual_first = ordinates[0] * yfactor  # FIRSTY is in real units (post-YFACTOR)
        if abs(actual_first - firsty) > 1e-3 * abs(firsty) + 1e-6:
            raise ValueError(f"ASDF FIRSTY mismatch: decoded {actual_first} != {firsty}")

    firstx = ldr_float(ldrs, "FIRSTX")
    lastx = ldr_float(ldrs, "LASTX")
    if firstx is not None and lastx is not None and n > 1:
        step = (lastx - firstx) / (n - 1)
        # data runs FIRSTX->LASTX when the leading index ascends, else LASTX->FIRSTX
        x = [firstx + j * step for j in range(n)] if direction >= 0 \
            else [lastx - j * step for j in range(n)]
    else:
        x = [(x0 + direction * j) * xfactor for j in range(n)]
    y = [v * yfactor for v in ordinates]
    return x, y
