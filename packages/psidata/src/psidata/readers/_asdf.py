"""Decoder for JCAMP-DX ASDF-compressed ordinate data — the ``(X++(Y..Y))`` form.

ASDF packs integer Y values as ASCII pseudo-digits:

* **SQZ** (squeezed absolute): first digit's sign+value is a single char — ``@ABCDEFGHI`` = +0..+9,
  ``abcdefghi`` = −1..−9; remaining digits are plain.
* **DIF** (difference from the previous Y): ``%JKLMNOPQR`` = +0..+9, ``jklmnopqr`` = −1..−9.
* **DUP** (duplicate the previous action N times): ``STUVWXYZs`` = 1..9 (plus trailing digits).

In ``(X++(Y..Y))`` each line begins with the abscissa *index* of its first ordinate, and
consecutive lines **overlap by one point** (the last ordinate of a line is repeated as a check at
the start of the next). Validated against real Bruker ``.jdx`` files (65536- and 131072-point
spectra): decoded counts, the per-line Y-value checks, and ``FIRSTY`` all match the headers.
"""

from __future__ import annotations

_SQZ_POS = "@ABCDEFGHI"
_SQZ_NEG = "abcdefghi"
_DIF_POS = "%JKLMNOPQR"
_DIF_NEG = "jklmnopqr"
_DUP = "STUVWXYZs"


def _tokenize(line: str) -> list[tuple[str, int | float]]:
    """Split one ASDF line into (kind, value) tokens. kind ∈ {ABS, DIF, DUP}."""
    tokens: list[tuple[str, int | float]] = []
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c in " \t,;":
            i += 1
            continue
        if c in _SQZ_POS or c in _SQZ_NEG:
            digit, sign, kind = (_SQZ_POS.index(c), 1, "ABS") if c in _SQZ_POS \
                else (_SQZ_NEG.index(c) + 1, -1, "ABS")
        elif c in _DIF_POS or c in _DIF_NEG:
            digit, sign, kind = (_DIF_POS.index(c), 1, "DIF") if c in _DIF_POS \
                else (_DIF_NEG.index(c) + 1, -1, "DIF")
        elif c in _DUP:
            digit, sign, kind = _DUP.index(c) + 1, 1, "DUP"
        elif c.isdigit() or c in "+-.":
            sign = 1
            if c == "+":
                i += 1
            elif c == "-":
                sign, i = -1, i + 1
            start = i
            while i < n and (line[i].isdigit() or line[i] == "."):
                i += 1
            num = line[start:i]
            if num:
                tokens.append(("ABS", sign * (float(num) if "." in num else int(num))))
            continue
        else:
            i += 1
            continue
        i += 1
        rest = ""
        while i < n and line[i].isdigit():
            rest += line[i]
            i += 1
        tokens.append((kind, sign * int(f"{digit}{rest}")))
    return tokens


def _line_ordinates(tokens: list[tuple[str, int | float]]) -> list[int | float]:
    """Decode a line's ordinate stream (tokens after the leading abscissa)."""
    ys: list[int | float] = []
    prev: int | float | None = None
    last_dif: int | float | None = None
    for kind, value in tokens[1:]:
        if kind == "ABS":
            prev, last_dif = value, None
            ys.append(prev)
        elif kind == "DIF":
            prev = prev + value
            last_dif = value
            ys.append(prev)
        elif kind == "DUP":  # repeat the previous action: re-apply the difference, or repeat value
            for _ in range(int(value) - 1):
                if last_dif is not None:
                    prev = prev + last_dif
                ys.append(prev)
    return ys


def decode_xpp_yy(data_lines: list[str], npoints: int | None = None
                  ) -> tuple[int | float | None, int, list[int | float]]:
    """Decode ``(X++(Y..Y))`` data lines into ``(x0, direction, ordinates)``.

    Two vendor conventions for the line boundary are both handled:

    * **overlapping** (Bruker) — the last ordinate of a line is repeated as the first ordinate of
      the next (a Y-value check); the duplicate is dropped.
    * **contiguous** (Nicolet) — lines simply abut, no shared point.

    ``npoints`` (from the header) disambiguates which convention applies; without it, overlap is
    inferred from whether consecutive line boundaries coincide.
    """
    per_line: list[tuple[int | float, list[int | float]]] = []
    for raw in data_lines:
        line = raw.strip()
        if not line or line.startswith(("##", "$$")):
            continue
        tokens = _tokenize(line)
        if not tokens:
            continue
        ys = _line_ordinates(tokens)
        if ys:
            per_line.append((tokens[0][1], ys))
    if not per_line:
        return None, -1, []

    total = sum(len(ys) for _, ys in per_line)
    n_boundaries = len(per_line) - 1
    if npoints is not None:
        if total == npoints:
            overlap: bool | None = False
        elif total - n_boundaries == npoints:
            overlap = True
        else:
            # Some real exports (e.g. edited Chemotion JCAMP) match neither convention exactly —
            # mixed/duplicated boundaries. Rather than reject the spectrum, de-overlap adaptively:
            # drop only the line boundaries whose first ordinate actually repeats the previous value.
            overlap = None
    else:
        overlap = len(per_line) > 1 and per_line[1][1][0] == per_line[0][1][-1]

    ordinates: list[int | float] = []
    for idx, (_lead, ys) in enumerate(per_line):
        if ordinates:
            if overlap is True:
                if ys[0] != ordinates[-1]:
                    raise ValueError(
                        f"ASDF Y-value check failed at data line {idx}: {ys[0]} != {ordinates[-1]}"
                    )
                ys = ys[1:]
            elif overlap is None and ys[0] == ordinates[-1]:
                ys = ys[1:]
        ordinates.extend(ys)

    leads = [lead for lead, _ in per_line]
    direction = 1 if (len(leads) >= 2 and leads[1] > leads[0]) else -1
    return per_line[0][0], direction, ordinates
