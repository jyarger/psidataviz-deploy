"""Read files from a public **Codeberg** repository (Gitea-based git host).

Gitea's REST API mirrors GitHub's: one call resolves the default branch and one recursive git-tree call
lists every file. Raw bytes come from ``codeberg.org/{owner}/{repo}/raw/branch/{ref}/{path}``. Like
``GitHubSource``, contents are fetched lazily. A read-only ``CODEBERG_TOKEN`` raises the rate limit but is
optional for public repos.
"""

from __future__ import annotations

import os
import re

import httpx

from .base import DataSource, FileRef
from .github import RepoRef

API = "https://codeberg.org/api/v1"
WEB = "https://codeberg.org"

_CODEBERG_URL_RE = re.compile(
    r"""^https?://codeberg\.org/
        (?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?
        (?:/src/branch/(?P<ref>[^/\s]+)(?:/(?P<subpath>.+))?)?
        /?$""",
    re.VERBOSE,
)


class CodebergError(RuntimeError):
    """Raised when the Codeberg/Gitea API call fails (bad repo, rate limit, network)."""


def parse_codeberg_url(url: str) -> RepoRef:
    """Parse a Codeberg URL, optionally ``/src/branch/<ref>/<subdir>``."""
    m = _CODEBERG_URL_RE.match(url.strip())
    if not m:
        raise ValueError(f"Not a recognizable Codeberg repo reference: {url!r}")
    return RepoRef(owner=m["owner"], repo=m["repo"], ref=m["ref"],
                   subpath=m["subpath"].rstrip("/") if m["subpath"] else None)


class CodebergSource(DataSource):
    def __init__(self, url: str, *, token: str | None = None, client: httpx.Client | None = None,
                 timeout: float = 30.0):
        self.repo = parse_codeberg_url(url)
        self.token = token or os.environ.get("CODEBERG_TOKEN")
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None
        self.label = f"codeberg:{self.repo.owner}/{self.repo.repo}"
        self._resolved_ref: str | None = self.repo.ref

    def __enter__(self) -> CodebergSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _get(self, url: str) -> httpx.Response:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        try:
            resp = self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise CodebergError(f"Request to {url} failed: {exc}") from exc
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise CodebergError("Codeberg API rate limit hit. Set CODEBERG_TOKEN to raise the limit.")
        if resp.status_code >= 400:
            raise CodebergError(f"Codeberg API {resp.status_code} for {url}: {resp.text[:200]}")
        return resp

    def resolve_ref(self) -> str:
        if self._resolved_ref:
            return self._resolved_ref
        data = self._get(f"{API}/repos/{self.repo.owner}/{self.repo.repo}").json()
        self._resolved_ref = data.get("default_branch", "main")
        return self._resolved_ref

    def list_files(self) -> list[FileRef]:
        ref = self.resolve_ref()
        url = f"{API}/repos/{self.repo.owner}/{self.repo.repo}/git/trees/{ref}?recursive=true&per_page=99999"
        tree = self._get(url).json().get("tree", [])
        prefix = f"{self.repo.subpath}/" if self.repo.subpath else ""
        refs: list[FileRef] = []
        for node in tree:
            if node.get("type") != "blob":
                continue
            path = node["path"]
            if prefix and not path.startswith(prefix):
                continue
            refs.append(FileRef(
                path=path, size=node.get("size"),
                download_url=f"{WEB}/{self.repo.owner}/{self.repo.repo}/raw/branch/{ref}/{path}",
            ))
        return refs

    def open_bytes(self, ref: FileRef) -> bytes:
        return self._get(ref.download_url).content

    def open_text(self, ref: FileRef) -> str:
        resp = self._get(ref.download_url)
        resp.encoding = resp.encoding or "utf-8"
        return resp.text
