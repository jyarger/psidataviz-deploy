"""The data-source contract: *where* files come from, independent of *how* they're parsed.

v1 ships :class:`~psidata.sources.github.GitHubSource`. Drive / URL / upload sources implement the
same interface and slot in without touching the catalog or app.
"""

from __future__ import annotations

import posixpath
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class FileRef:
    """A file discovered in a source, described cheaply (no content downloaded yet)."""

    path: str  # full path within the source, e.g. "DSC/2023_06_14_Indium_wire_std.txt"
    size: int | None = None
    download_url: str | None = None  # direct URL to raw bytes, when available

    @property
    def name(self) -> str:
        return posixpath.basename(self.path)

    @property
    def ext(self) -> str:
        return posixpath.splitext(self.name)[1].lower()

    @property
    def top_dir(self) -> str:
        """First path component — by convention the instrument/method folder (DSC, FTIR, ...)."""
        parts = self.path.split("/")
        return parts[0] if len(parts) > 1 else ""


class DataSource(ABC):
    """Abstract source of data files."""

    #: Human-readable label for the source (shown in the UI).
    label: str = "source"

    @abstractmethod
    def list_files(self) -> list[FileRef]:
        """List all files available from this source (metadata only)."""

    @abstractmethod
    def open_text(self, ref: FileRef) -> str:
        """Fetch and decode a file's contents as text."""

    @abstractmethod
    def open_bytes(self, ref: FileRef) -> bytes:
        """Fetch a file's raw bytes."""
