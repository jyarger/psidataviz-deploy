"""Read files from a **public** Google Drive folder — keyless, no API key required.

A Drive folder shared as "anyone with the link" exposes an ``embeddedfolderview`` HTML listing that
needs no authentication: each folder's page lists its entries (sub-folders link to
``/drive/folders/{id}``, files to ``/file/d/{id}``), and file bytes download from
``uc?export=download&id={id}``. We walk the tree breadth-first (folders fetched concurrently) and
emit one :class:`~psidata.sources.base.FileRef` per file, so a Drive folder plugs into the same
catalog / records / reader machinery as :class:`~psidata.sources.github.GitHubSource`.

Large files (>~100 MB) that trigger Drive's virus-scan interstitial are handled in
:meth:`GoogleDriveSource.open_bytes`; the small/medium text formats we actually parse download
directly.
"""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

from .base import DataSource, FileRef

# folder id from /drive/folders/<id>, ?id=<id>, /folderview?id=<id>, or a bare id
_FOLDER_ID_RE = re.compile(r"(?:/folders/|[?&]id=)([A-Za-z0-9_-]{20,})")
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")
# one entry: id="entry-<id>" ... href="https://drive.google.com/<href>" ... flip-entry-title"><name>
_ENTRY_RE = re.compile(
    r'id="entry-([^"]+)"[^>]*>.*?'
    r'href="https://drive\.google\.com/([^"]+)".*?'
    r'flip-entry-title">([^<]+)',
    re.S,
)

_FOLDER_VIEW = "https://drive.google.com/embeddedfolderview?id={}#list"
_DOWNLOAD = "https://drive.google.com/uc?export=download&id={}"


def download_drive(url: str, *, client: httpx.Client | None = None) -> bytes:
    """Fetch a Drive ``uc?export=download`` URL, following the large-file virus-scan **confirm**
    interstitial (an HTML form) when Drive can't scan the file — so big archives download in full."""
    own = client is None
    client = client or httpx.Client(timeout=120.0, follow_redirects=True)
    try:
        resp = client.get(url)
        resp.raise_for_status()
        if resp.headers.get("content-type", "").startswith("text/html"):
            action = re.search(r'action="([^"]+)"', resp.text)
            if action:  # re-issue the download through the confirm form's action + hidden fields
                params = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', resp.text))
                resp = client.get(html.unescape(action.group(1)), params=params)
                resp.raise_for_status()
        return resp.content
    finally:
        if own:
            client.close()
_UA = "Mozilla/5.0 (compatible; PsiData/1.0)"


class GoogleDriveError(RuntimeError):
    """Raised when a Drive folder can't be listed or a file can't be fetched."""


def parse_drive_url(url: str) -> str:
    """Extract the folder id from a Drive folder URL (or accept a bare folder id)."""
    s = url.strip()
    m = _FOLDER_ID_RE.search(s)
    if m:
        return m.group(1)
    if _BARE_ID_RE.match(s):
        return s
    raise ValueError(f"Not a recognizable Google Drive folder reference: {url!r}")


class GoogleDriveSource(DataSource):
    def __init__(self, url: str, *, client: httpx.Client | None = None, timeout: float = 30.0,
                 max_folders: int = 600, max_workers: int = 8):
        self.folder_id = parse_drive_url(url)
        self._client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": _UA}
        )
        self._owns_client = client is None
        self.max_folders = max_folders
        self.max_workers = max_workers
        self.label = f"gdrive:{self.folder_id}"

    # -- context management so callers can close the http client --------------------------------
    def __enter__(self) -> GoogleDriveSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _list_folder(self, folder_id: str) -> list[tuple[str, str, str]]:
        """Return ``(kind, id, name)`` for each entry; ``kind`` is ``"folder"`` or ``"file"``.

        Resilient: a single unreadable sub-folder yields ``[]`` rather than failing the whole scan.
        """
        try:
            resp = self._client.get(_FOLDER_VIEW.format(folder_id))
            resp.raise_for_status()
        except httpx.HTTPError:
            return []
        out: list[tuple[str, str, str]] = []
        for eid, href, name in _ENTRY_RE.findall(resp.text):
            kind = "folder" if "/folders/" in href else "file"
            out.append((kind, eid, html.unescape(name).strip()))
        return out

    def list_files(self) -> list[FileRef]:
        files: list[FileRef] = []
        level: list[tuple[str, str]] = [(self.folder_id, "")]  # (folder_id, path_prefix)
        fetched = 0
        while level and fetched < self.max_folders:
            batch = level[: self.max_folders - fetched]
            level = level[len(batch):]
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                listings = list(ex.map(lambda b: self._list_folder(b[0]), batch))
            fetched += len(batch)
            for (_fid, prefix), entries in zip(batch, listings, strict=True):
                for kind, eid, name in entries:
                    path = f"{prefix}{name}"
                    if kind == "folder":
                        level.append((eid, f"{path}/"))
                    else:
                        files.append(FileRef(path=path, download_url=_DOWNLOAD.format(eid)))
        return files

    def open_bytes(self, ref: FileRef) -> bytes:
        url = ref.download_url or _DOWNLOAD.format(ref.path)
        try:
            return download_drive(url, client=self._client)
        except httpx.HTTPError as exc:
            raise GoogleDriveError(f"Drive download failed for {ref.name!r}: {exc}") from exc

    def open_text(self, ref: FileRef) -> str:
        return self.open_bytes(ref).decode("utf-8", errors="replace")
