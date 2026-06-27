"""Reader registry + confidence-scored auto-detection.

Adding a technique never touches this file: a reader registers itself by decorating its class
with ``@register_reader``. Detection asks every reader to ``sniff`` and picks the best score.
"""

from __future__ import annotations

from .readers.base import BaseReader, Candidate

#: Minimum confidence required before we trust a reader with a file.
DETECT_THRESHOLD = 0.4

_READERS: list[BaseReader] = []


class UnknownFormatError(Exception):
    """Raised when no registered reader is confident enough to parse a candidate."""


def register_reader(cls: type[BaseReader]) -> type[BaseReader]:
    """Class decorator: instantiate the reader and add it to the registry."""
    _READERS.append(cls())
    return cls


def get_readers() -> list[BaseReader]:
    return list(_READERS)


def score_readers(candidate: Candidate) -> list[tuple[BaseReader, float]]:
    """Every reader's confidence for ``candidate``, sorted high to low."""
    scored = [(r, r.sniff(candidate)) for r in _READERS]
    scored.sort(key=lambda rs: rs[1], reverse=True)
    return scored


def detect(candidate: Candidate, threshold: float = DETECT_THRESHOLD) -> BaseReader | None:
    """Return the best-matching reader, or ``None`` if none clears ``threshold``."""
    scored = score_readers(candidate)
    if scored and scored[0][1] >= threshold:
        return scored[0][0]
    return None


def read(candidate: Candidate, threshold: float = DETECT_THRESHOLD):
    """Detect the right reader and parse ``candidate`` into a ``Dataset``."""
    reader = detect(candidate, threshold)
    if reader is None:
        best = score_readers(candidate)
        hint = f" best guess scored {best[0][1]:.2f} ({best[0][0].name})" if best else ""
        raise UnknownFormatError(f"No reader confident enough for {candidate.filename!r}.{hint}")
    return reader.read(candidate)
