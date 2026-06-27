"""Data sources: where files come from. GitHub first; the interface is source-agnostic."""

from __future__ import annotations

from .base import DataSource, FileRef
from .box import BoxError, BoxSource, parse_box_url
from .catalog import Catalog, CatalogEntry, build_entry, canonical_technique, scan
from .chemotion import ChemotionError, ChemotionSource, parse_chemotion_url
from .codeberg import CodebergError, CodebergSource, parse_codeberg_url
from .gdrive import GoogleDriveError, GoogleDriveSource, parse_drive_url
from .github import GitHubError, GitHubSource, RepoRef, parse_repo_url
from .records import (
    DataRecord,
    FormatInfo,
    FormatVariant,
    build_records,
    classify_format,
    record_key,
)


def make_source(url: str, **kwargs) -> DataSource:
    """Pick the right :class:`DataSource` for a URL (Chemotion / Google Drive / Codeberg / Box / GitHub)."""
    if "chemotion" in url.lower():
        return ChemotionSource(url, **kwargs)
    if "drive.google.com" in url:
        return GoogleDriveSource(url, **kwargs)
    if "codeberg.org" in url:
        return CodebergSource(url, **kwargs)
    if "box.com" in url:
        return BoxSource(url, **kwargs)
    return GitHubSource(url, **kwargs)


__all__ = [
    "BoxError",
    "BoxSource",
    "Catalog",
    "CatalogEntry",
    "ChemotionError",
    "ChemotionSource",
    "CodebergError",
    "CodebergSource",
    "DataRecord",
    "DataSource",
    "FileRef",
    "FormatInfo",
    "FormatVariant",
    "GitHubError",
    "GitHubSource",
    "GoogleDriveError",
    "GoogleDriveSource",
    "RepoRef",
    "build_entry",
    "build_records",
    "canonical_technique",
    "classify_format",
    "make_source",
    "parse_box_url",
    "parse_chemotion_url",
    "parse_codeberg_url",
    "parse_drive_url",
    "parse_repo_url",
    "record_key",
    "scan",
]
