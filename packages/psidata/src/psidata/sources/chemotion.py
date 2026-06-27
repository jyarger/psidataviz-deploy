"""Read published analytical data from the **Chemotion Repository** (https://www.chemotion-repository.net).

Chemotion is an open chemistry ELN + repository. Its public REST API (no auth) exposes published
molecules and reactions; each published *sample* links a downloadable **BagIt** zip that bundles the
sample's analyses (1H/13C/19F NMR, IR, MS …) as JCAMP-DX files plus metadata. We list each analysis as a
single file under its technique folder, and address the actual spectrum *inside* the zip with a
``<zip-url>!<member>`` download URL — the backend extracts the member (and caches the zip), so Chemotion
data flows through the same scan / records / read pipeline as any other source.

Supported inputs (``make_source`` routes any URL containing ``chemotion``):

* a molecule id — ``chemotion:3369``, ``…/molecules/3369``, ``…?id=3369``;
* an InChIKey or a Chemotion DOI (``10.14272/<InChIKey>.<n>``) — resolved against the public list;
* the repository home / a collection / a bare ``chemotion`` — browses the most recent published molecules.
"""

from __future__ import annotations

import io
import os
import re
import zipfile

import httpx

from .base import DataSource, FileRef

API = "https://www.chemotion-repository.net/api/v1/public"
#: separator joining a zip's URL to a member path inside it (the backend splits on ``.zip!``)
ZIP_MEMBER_SEP = "!"

_MOL_ID_RE = re.compile(r"/molecules?/(\d+)")
_QUERY_ID_RE = re.compile(r"[?&](?:id|mid|mol(?:ecule)?_?id)=(\d+)")
_INT_RE = re.compile(r"^\d+$")
_INCHIKEY_RE = re.compile(r"[A-Z]{14}-[A-Z]{10}-[A-Z]")

# Map a Chemotion analysis name (e.g. "1H NMR", "Mass", "DEPT135", "Me2BuLa_COSY") to a PsiData
# technique folder. We tokenise on separators (incl. "_") and match whole tokens, so "Weird" isn't read
# as "IR" and a sample-prefixed "Me2BuLa_HSQC" still resolves to NMR.
_NMR_TOKENS = {
    "NMR", "DEPT", "DEPT135", "DEPT90", "DEPT45", "APT", "COSY", "HSQC", "HMQC", "HMBC", "NOESY",
    "ROESY", "TOCSY", "JRES", "INADEQUATE", "NOE",
}
_TECH_TOKEN_MAP = (
    (_NMR_TOKENS, "NMR"),
    ({"MASS", "MS", "MALDI", "ESI", "GCMS", "LCMS", "HRMS"}, "Mass Spec"),
    ({"IR", "FTIR", "ATR"}, "FTIR"),
    ({"RAMAN"}, "Raman"),
    ({"UV", "VIS", "UVVIS"}, "UV-Vis"),
    ({"HPLC", "GC", "LC"}, "HPLC"),
)


class ChemotionError(RuntimeError):
    """Raised when the Chemotion API/download fails or a reference can't be resolved."""


def parse_chemotion_url(url: str) -> dict:
    """Resolve a Chemotion reference to ``{"kind": "molecule"|"inchikey"|"browse", ...}``."""
    u = url.strip()
    m = _MOL_ID_RE.search(u) or _QUERY_ID_RE.search(u)
    if m:
        return {"kind": "molecule", "id": int(m.group(1))}
    if u.lower().startswith("chemotion:"):
        tail = u.split(":", 1)[1].strip()
        if _INT_RE.match(tail):
            return {"kind": "molecule", "id": int(tail)}
    ik = _INCHIKEY_RE.search(u)
    if ik:
        return {"kind": "inchikey", "inchikey": ik.group(0)}
    if "chemotion" in u.lower():
        return {"kind": "browse"}
    raise ValueError(f"Not a recognizable Chemotion reference: {url!r}")


def _tech_folder(analysis_name: str) -> str:
    name = analysis_name or ""
    tokens = {t.upper() for t in re.split(r"[\s_/.+-]+", name) if t}
    for keywords, folder in _TECH_TOKEN_MAP:
        if tokens & keywords:
            return folder
    return name or "Analysis"


def _pick_member(zf: zipfile.ZipFile, members: list[str]) -> str | None:
    """The member that best represents an analysis: prefer a processed/edited or raw spectrum over a
    peak list, and only return one the reader registry actually recognises."""
    from ..readers.base import Candidate
    from ..registry import detect

    def rank(m: str) -> int:
        low = m.lower()
        if low.endswith(".edit.jdx"):
            return 0
        if low.endswith(".dx"):
            return 1
        if low.endswith(".jdx") and ".peak." not in low:
            return 2
        if low.endswith(".peak.jdx"):
            return 3
        return 9

    for m in sorted((m for m in members if rank(m) < 9), key=rank):
        try:
            if detect(Candidate(filename=os.path.basename(m), content=zf.read(m))) is not None:
                return m
        except Exception:  # noqa: BLE001  a malformed member must not abort the listing
            continue
    return None


class ChemotionSource(DataSource):
    def __init__(self, url: str, *, client: httpx.Client | None = None, timeout: float = 120.0,
                 max_molecules: int = 3):
        self.target = parse_chemotion_url(url)
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True,
                                              headers={"User-Agent": "psidata"})
        self._owns_client = client is None
        self.max_molecules = max_molecules
        self.label = "chemotion:" + (str(self.target.get("id")) if self.target["kind"] == "molecule"
                                     else self.target.get("inchikey", "repository"))
        self._zips: dict[str, zipfile.ZipFile] = {}

    def __enter__(self) -> ChemotionSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # --- API helpers ----------------------------------------------------------------------------
    def _get_json(self, path: str) -> dict:
        try:
            resp = self._client.get(API + path, headers={"Accept": "application/json"})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise ChemotionError(f"Chemotion API request failed ({path}): {exc}") from exc

    def _zip(self, zip_url: str) -> zipfile.ZipFile:
        if zip_url not in self._zips:
            try:
                resp = self._client.get(zip_url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ChemotionError(f"Could not download Chemotion archive {zip_url}: {exc}") from exc
            self._zips[zip_url] = zipfile.ZipFile(io.BytesIO(resp.content))
        return self._zips[zip_url]

    def _molecule_ids(self) -> list[int]:
        kind = self.target["kind"]
        if kind == "molecule":
            return [self.target["id"]]
        if kind == "inchikey":
            key = self.target["inchikey"]
            for page in range(1, 6):  # best-effort lookup over the first few pages
                mols = self._get_json(f"/molecules?page={page}").get("molecules", [])
                if not mols:
                    break
                hit = next((m for m in mols if m.get("inchikey") == key), None)
                if hit:
                    return [hit["id"]]
            raise ChemotionError(
                f"Couldn't find published molecule {key} in the recent Chemotion list — "
                "try the numeric molecule id, or browse the repository."
            )
        mols = self._get_json(f"/molecules?per_page={self.max_molecules}").get("molecules", [])
        return [m["id"] for m in mols[: self.max_molecules]]

    # --- DataSource interface -------------------------------------------------------------------
    def list_files(self) -> list[FileRef]:
        refs: list[FileRef] = []
        for mid in self._molecule_ids():
            detail = self._get_json(f"/molecule?id={mid}")
            for sample in detail.get("published_samples", []):
                refs.extend(self._sample_refs(sample))
        return refs

    def _sample_refs(self, sample: dict) -> list[FileRef]:
        zip_url = sample.get("zip_download_url")
        if not zip_url:
            return []
        label = sample.get("short_label") or sample.get("name") or "sample"
        # map each analysis folder (analysis_<id>) to its technique via the API container tree
        techniques: dict[int, str] = {}
        try:
            for analysis in sample["container"]["children"][0]["children"]:
                techniques[analysis["id"]] = analysis.get("name") or "Analysis"
        except (KeyError, IndexError, TypeError):
            pass

        zf = self._zip(zip_url)
        by_folder: dict[str, list[str]] = {}
        for name in zf.namelist():
            if "/analysis_" in name and not name.endswith("/"):
                by_folder.setdefault(name.rsplit("/", 1)[0], []).append(name)

        refs: list[FileRef] = []
        for folder, members in sorted(by_folder.items()):
            inner = _pick_member(zf, members)
            if inner is None:
                continue
            aid = _analysis_id(folder)
            analysis_name = techniques.get(aid, "Analysis")
            tech = _tech_folder(analysis_name)
            ext = os.path.splitext(inner)[1] or ".jdx"
            path = f"{tech}/{label} {analysis_name}{ext}"
            refs.append(FileRef(
                path=path,
                size=zf.getinfo(inner).file_size,
                download_url=f"{zip_url}{ZIP_MEMBER_SEP}{inner}",
            ))
        return refs

    def _member_for(self, ref: FileRef) -> tuple[str, str]:
        zip_url, _, member = ref.download_url.partition(ZIP_MEMBER_SEP)
        return zip_url, member

    def open_bytes(self, ref: FileRef) -> bytes:
        zip_url, member = self._member_for(ref)
        return self._zip(zip_url).read(member)

    def open_text(self, ref: FileRef) -> str:
        return self.open_bytes(ref).decode("latin-1", errors="replace")


def _analysis_id(folder: str) -> int:
    m = re.search(r"/analysis_(\d+)", folder)
    return int(m.group(1)) if m else -1
