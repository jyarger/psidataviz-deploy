"""Parse the lab's filename convention: ``YYYY_MM_DD_<underscore_separated_description>``.

Filenames are a cheap, reliable source of metadata (date + sample/run description) that lets the
catalog summarize a repo without opening every file.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date

_DATE_RE = re.compile(r"^(\d{4})_(\d{2})_(\d{2})(?:_(.*))?$")


@dataclass
class ParsedName:
    stem: str
    date: date | None = None
    description: str = ""
    tokens: list[str] = field(default_factory=list)

    @property
    def has_date(self) -> bool:
        return self.date is not None


def parse_filename(name: str) -> ParsedName:
    """Extract a leading ``YYYY_MM_DD`` date (if present) and a human description from a filename."""
    stem = os.path.splitext(os.path.basename(name))[0]
    m = _DATE_RE.match(stem)
    if m:
        year, month, day, rest = m.groups()
        rest = rest or ""
        try:
            parsed_date: date | None = date(int(year), int(month), int(day))
        except ValueError:
            parsed_date, rest = None, stem
    else:
        parsed_date, rest = None, stem

    tokens = [t for t in rest.split("_") if t]
    return ParsedName(
        stem=stem,
        date=parsed_date,
        description=" ".join(tokens),
        tokens=tokens,
    )
