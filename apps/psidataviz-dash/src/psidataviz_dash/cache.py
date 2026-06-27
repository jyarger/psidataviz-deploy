"""Tiny on-disk cache for fetched files and repo listings (keeps the stateless app fast).

No database — just content-addressed files under the user cache dir. Set ``PSIDATA_NO_CACHE=1`` to
disable (useful in tests).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import platformdirs

CACHE_DIR = Path(os.environ.get("PSIDATA_CACHE_DIR", platformdirs.user_cache_dir("psidata")))


def _enabled() -> bool:
    return os.environ.get("PSIDATA_NO_CACHE", "") not in ("1", "true", "True")


def _path(namespace: str, key: str, suffix: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    folder = CACHE_DIR / namespace
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{digest}{suffix}"


def get_text(namespace: str, key: str) -> str | None:
    if not _enabled():
        return None
    path = _path(namespace, key, ".txt")
    return path.read_text(encoding="utf-8") if path.exists() else None


def set_text(namespace: str, key: str, value: str) -> None:
    if not _enabled():
        return
    _path(namespace, key, ".txt").write_text(value, encoding="utf-8")


def get_json(namespace: str, key: str) -> Any | None:
    if not _enabled():
        return None
    path = _path(namespace, key, ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def set_json(namespace: str, key: str, value: Any) -> None:
    if not _enabled():
        return
    _path(namespace, key, ".json").write_text(json.dumps(value), encoding="utf-8")
