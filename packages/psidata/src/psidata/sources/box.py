"""Read files from a public **Box** shared folder — keyless, no API token.

Box renders each folder's contents into the page as a ``Box.postStreamData`` JSON blob. We walk the
shared folder by fetching ``/s/<sharedName>`` and ``/s/<sharedName>/folder/<id>`` pages, collect the
file/folder items belonging to the current folder, and download bytes from the keyless
``index.php?rm=box_download_shared_file`` endpoint (a normal HTTP URL, so the rest of the app needs no
changes).
"""

from __future__ import annotations

import json
import re

import httpx

from .base import DataSource, FileRef

WEB = "https://app.box.com"
_BOX_URL_RE = re.compile(r"box\.com/s/(?P<sn>[A-Za-z0-9]+)")
_CURRENT_RE = re.compile(r'"currentFolderID":"?(\d+)"?')


class BoxError(RuntimeError):
    """Raised when a Box shared folder can't be read (bad link, removed share, network)."""


def parse_box_url(url: str) -> str:
    """Extract the shared-link token from a ``app.box.com/s/<sharedName>`` URL."""
    m = _BOX_URL_RE.search(url.strip())
    if not m:
        raise ValueError(f"Not a recognizable Box shared-folder URL: {url!r}")
    return m["sn"]


class BoxSource(DataSource):
    def __init__(self, url: str, *, client: httpx.Client | None = None, timeout: float = 30.0,
                 max_depth: int = 8):
        self.shared_name = parse_box_url(url)
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True,
                                              headers={"User-Agent": "Mozilla/5.0 (PsiDataViz)"})
        self._owns_client = client is None
        self.label = f"box:{self.shared_name}"
        self._max_depth = max_depth

    def __enter__(self) -> BoxSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _page(self, folder_id: int | None) -> str:
        url = f"{WEB}/s/{self.shared_name}" + (f"/folder/{folder_id}" if folder_id else "")
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            raise BoxError(f"Request to {url} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise BoxError(f"Box returned {resp.status_code} for {url} (is the link public?)")
        return resp.text

    def list_files(self) -> list[FileRef]:
        refs: list[FileRef] = []
        self._walk(None, "", refs, 0, set())
        return refs

    def _walk(self, folder_id: int | None, prefix: str, refs: list[FileRef], depth: int,
              seen: set[int]) -> None:
        if depth > self._max_depth:
            return
        html = self._page(folder_id)
        current = _current_folder_id(html)
        if current is None or current in seen:
            return
        seen.add(current)
        for item in _items(html, current):
            if item["type"] == "folder":
                self._walk(item["id"], f"{prefix}{item['name']}/", refs, depth + 1, seen)
            else:
                refs.append(FileRef(
                    path=f"{prefix}{item['name']}", size=item.get("size"),
                    download_url=(f"{WEB}/index.php?rm=box_download_shared_file"
                                  f"&shared_name={self.shared_name}&file_id=f_{item['id']}"),
                ))

    def open_bytes(self, ref: FileRef) -> bytes:
        return self._client.get(ref.download_url).content

    def open_text(self, ref: FileRef) -> str:
        resp = self._client.get(ref.download_url)
        resp.encoding = resp.encoding or "utf-8"
        return resp.text


def _current_folder_id(html: str) -> int | None:
    m = _CURRENT_RE.search(html)
    return int(m.group(1)) if m else None


def _poststream(html: str) -> dict:
    """Extract the ``Box.postStreamData = {...}`` JSON object (brace-balanced, string-aware)."""
    anchor = html.find("Box.postStreamData")
    if anchor < 0:
        return {}
    start = html.find("{", anchor)
    if start < 0:
        return {}
    depth = 0
    in_str = False
    escaped = False
    for k in range(start, len(html)):
        c = html[k]
        if in_str:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:k + 1])
                except json.JSONDecodeError:
                    return {}
    return {}


def _items(html: str, current_folder_id: int) -> list[dict]:
    """File/folder items that are direct children of ``current_folder_id`` (excludes breadcrumbs)."""
    data = _poststream(html)
    out: list[dict] = []
    seen: set[int] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            tid, typ, name = node.get("typedID"), node.get("type"), node.get("name")
            parent = node.get("parentFolderID")
            if (tid and typ in ("file", "folder") and name and parent is not None
                    and _as_int(parent) == current_folder_id and node.get("id") not in seen):
                seen.add(node["id"])
                out.append({"id": _as_int(node["id"]), "name": name, "type": typ,
                            "size": node.get("itemSize")})
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return out


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
