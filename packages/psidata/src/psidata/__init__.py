"""PsiData (Ψ Data) — a framework-agnostic library for ingesting, parsing, and converting
experimental & computational scientific data into one universal model.
"""

from __future__ import annotations

from . import readers as _readers  # noqa: F401  (import registers all built-in readers)
from .archive import (
    ArchiveError,
    archive_datasets,
    is_archive,
    read_archive,
    read_zip,
    zip_datasets,
)
from .compare import Comparison, compare_datasets, compare_record_formats
from .convert import convert
from .filename import ParsedName, parse_filename
from .model import Audio, Axis, Dataset, Image2D, Metadata, Signal, SourceInfo, Structure3D, VibMode
from .readers.base import BaseReader, Candidate
from .registry import (
    UnknownFormatError,
    detect,
    get_readers,
    read,
    register_reader,
    score_readers,
)

__version__ = "0.2.0"

__all__ = [
    "ArchiveError",
    "archive_datasets",
    "Audio",
    "Axis",
    "BaseReader",
    "Candidate",
    "Comparison",
    "Dataset",
    "Image2D",
    "Metadata",
    "ParsedName",
    "is_archive",
    "read_archive",
    "Signal",
    "SourceInfo",
    "Structure3D",
    "UnknownFormatError",
    "VibMode",
    "compare_datasets",
    "compare_record_formats",
    "convert",
    "detect",
    "get_readers",
    "parse_filename",
    "read",
    "read_zip",
    "register_reader",
    "zip_datasets",
    "score_readers",
    "__version__",
]
