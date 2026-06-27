"""The reader contract every technique parser implements.

A reader does two things:

* ``sniff(candidate) -> float`` — inspect a file's name and head, return a 0–1 confidence that
  this reader can parse it. The registry picks the highest-confidence reader.
* ``read(candidate) -> Dataset`` — fully parse the file into the universal :class:`Dataset`.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..model import Dataset


@dataclass
class Candidate:
    """A file to be sniffed/read, with content supplied as text and/or bytes."""

    filename: str
    text: str | None = None
    content: bytes | None = None
    uri: str | None = None
    #: Optional technique label from the source layout (e.g. the instrument folder name). For
    #: headerless formats (FTIR/Raman tables) this is often the only way to disambiguate; readers
    #: may use it to boost ``sniff`` confidence. Content-identifiable formats (DSC/NMR) ignore it.
    technique_hint: str | None = None

    @property
    def ext(self) -> str:
        return os.path.splitext(self.filename)[1].lower()

    @property
    def stem(self) -> str:
        return os.path.splitext(os.path.basename(self.filename))[0]

    def as_text(self) -> str:
        """Decode content to text once, tolerating odd encodings (instrument exports vary)."""
        if self.text is not None:
            return self.text
        if self.content is not None:
            for enc in ("utf-8", "utf-8-sig", "latin-1"):
                try:
                    self.text = self.content.decode(enc)
                    return self.text
                except UnicodeDecodeError:
                    continue
            self.text = self.content.decode("utf-8", errors="replace")
            return self.text
        return ""

    def head(self, n: int = 8192) -> str:
        return self.as_text()[:n]


class BaseReader(ABC):
    """Subclass this and decorate with ``@register_reader`` to add a new format."""

    technique: str = "unknown"
    name: str = "base"
    version: str = "0.0.0"
    #: File extensions this reader is likely to handle, for cheap catalog pre-filtering
    #: (real detection still goes through ``sniff`` on content).
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def sniff(self, candidate: Candidate) -> float:
        """Return a confidence in [0, 1] that this reader can parse ``candidate``."""

    @abstractmethod
    def read(self, candidate: Candidate) -> Dataset:
        """Parse ``candidate`` into a :class:`Dataset`. Assumes ``sniff`` was favorable."""
