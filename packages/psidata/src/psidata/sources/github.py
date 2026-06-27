"""Read files from a public GitHub repository.

Uses two cheap REST calls per scan: one to resolve the default branch (if not given) and one
recursive Git-tree call to list every file with its size. File contents are fetched lazily from
``raw.githubusercontent.com`` only when a dataset is actually opened.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

from .base import DataSource, FileRef

_GITHUB_URL_RE = re.compile(
    r"""^(?:https?://github\.com/)?    # optional host
        (?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?
        (?:/tree/(?P<ref>[^/\s]+)(?:/(?P<subpath>.+))?)?  # optional /tree/<ref>/<subpath>
        /?$""",
    re.VERBOSE,
)

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


class GitHubError(RuntimeError):
    """Raised when the GitHub API call fails (bad repo, rate limit, network)."""


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str
    ref: str | None = None
    subpath: str | None = None


def parse_repo_url(url: str) -> RepoRef:
    """Parse ``owner/repo``, a full GitHub URL, or a ``/tree/<branch>/<subdir>`` URL."""
    m = _GITHUB_URL_RE.match(url.strip())
    if not m:
        raise ValueError(f"Not a recognizable GitHub repo reference: {url!r}")
    return RepoRef(
        owner=m["owner"],
        repo=m["repo"],
        ref=m["ref"],
        subpath=m["subpath"].rstrip("/") if m["subpath"] else None,
    )


class GitHubSource(DataSource):
    def __init__(self, url: str, *, token: str | None = None, client: httpx.Client | None = None,
                 timeout: float = 30.0):
        self.repo = parse_repo_url(url)
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None
        self.label = f"github:{self.repo.owner}/{self.repo.repo}"
        self._resolved_ref: str | None = self.repo.ref

    # -- context management so callers can close the http client --------------------------------
    def __enter__(self) -> GitHubSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, url: str) -> httpx.Response:
        try:
            resp = self._client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:  # network-level
            raise GitHubError(f"Request to {url} failed: {exc}") from exc
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise GitHubError("GitHub API rate limit hit. Set GITHUB_TOKEN to raise the limit.")
        if resp.status_code >= 400:
            raise GitHubError(f"GitHub API {resp.status_code} for {url}: {resp.text[:200]}")
        return resp

    def resolve_ref(self) -> str:
        """Return the branch/ref to read, defaulting to the repo's default branch."""
        if self._resolved_ref:
            return self._resolved_ref
        data = self._get(f"{API}/repos/{self.repo.owner}/{self.repo.repo}").json()
        self._resolved_ref = data.get("default_branch", "main")
        return self._resolved_ref

    def list_files(self) -> list[FileRef]:
        ref = self.resolve_ref()
        url = f"{API}/repos/{self.repo.owner}/{self.repo.repo}/git/trees/{ref}?recursive=1"
        tree = self._get(url).json().get("tree", [])
        prefix = f"{self.repo.subpath}/" if self.repo.subpath else ""
        refs: list[FileRef] = []
        for node in tree:
            if node.get("type") != "blob":
                continue
            path = node["path"]
            if prefix and not path.startswith(prefix):
                continue
            refs.append(
                FileRef(
                    path=path,
                    size=node.get("size"),
                    download_url=f"{RAW}/{self.repo.owner}/{self.repo.repo}/{ref}/{path}",
                )
            )
        return refs

    def _raw_url(self, ref: FileRef) -> str:
        if ref.download_url:
            return ref.download_url
        branch = self.resolve_ref()
        return f"{RAW}/{self.repo.owner}/{self.repo.repo}/{branch}/{ref.path}"

    def open_bytes(self, ref: FileRef) -> bytes:
        return self._get(self._raw_url(ref)).content

    def open_text(self, ref: FileRef) -> str:
        resp = self._get(self._raw_url(ref))
        resp.encoding = resp.encoding or "utf-8"
        return resp.text
