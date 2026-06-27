"""Glue between the UI and the library: scan repos and load datasets, with caching.

Keeps the Dash callbacks thin and free of any networking / parsing detail.
"""

from __future__ import annotations

import os
from dataclasses import asdict

import httpx
from psidata import Candidate, Dataset, read, read_zip
from psidata.sources import Catalog, FileRef, GitHubSource
from psidata.sources.catalog import build_entry

from . import cache


def scan_repo(url: str, *, use_cache: bool = True) -> Catalog:
    """List a GitHub repo and build its catalog, caching the (cheap) file listing by URL."""
    payload = cache.get_json("listing", url) if use_cache else None
    if payload is None:
        with GitHubSource(url) as src:
            refs = src.list_files()
            label = src.label
        payload = {"label": label, "files": [asdict(r) for r in refs]}
        cache.set_json("listing", url, payload)

    refs = [FileRef(**f) for f in payload["files"]]
    entries = [build_entry(r) for r in refs]
    return Catalog(source_label=payload["label"], entries=entries)


def fetch_text(url: str, *, use_cache: bool = True) -> str:
    """Fetch a raw file's text, cached by URL."""
    cached = cache.get_text("file", url) if use_cache else None
    if cached is not None:
        return cached
    headers = {}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "githubusercontent" in url:
        headers["Authorization"] = f"Bearer {token}"
    resp = httpx.get(url, follow_redirects=True, timeout=60.0, headers=headers)
    resp.raise_for_status()
    text = resp.text
    cache.set_text("file", url, text)
    return text


def fetch_bytes(url: str) -> bytes:
    """Fetch a raw file's bytes (used for archives; not cached — they're large)."""
    headers = {}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "githubusercontent" in url:
        headers["Authorization"] = f"Bearer {token}"
    resp = httpx.get(url, follow_redirects=True, timeout=120.0, headers=headers)
    resp.raise_for_status()
    return resp.content


def load_dataset(name: str, url: str, *, technique: str | None = None,
                 use_cache: bool = True) -> Dataset:
    """Fetch and parse a single dataset into the universal model.

    ``technique`` (the source folder) is passed as a hint so headerless formats (FTIR/Raman) can
    be disambiguated; content-identifiable formats ignore it. ``.zip`` archives are unpacked.
    """
    if name.lower().endswith(".zip") or url.lower().endswith(".zip"):
        return read_zip(name, fetch_bytes(url), technique_hint=technique)
    text = fetch_text(url, use_cache=use_cache)
    return read(Candidate(filename=name, text=text, uri=url, technique_hint=technique))
