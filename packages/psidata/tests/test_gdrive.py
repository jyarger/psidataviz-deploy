"""GoogleDriveSource: folder-id parsing, keyless embeddedfolderview walk, source routing."""

from __future__ import annotations

import httpx
import pytest
import respx

from psidata.sources import FileRef, GitHubSource, GoogleDriveSource, make_source
from psidata.sources.gdrive import parse_drive_url


def _entry(eid: str, name: str, *, folder: bool) -> str:
    href = (
        f"https://drive.google.com/drive/folders/{eid}"
        if folder
        else f"https://drive.google.com/file/d/{eid}/view"
    )
    return (
        f'<div class="flip-entry" id="entry-{eid}">'
        f'<a href="{href}" target="_blank">'
        f'<div class="flip-entry-title">{name}</div></a></div>'
    )


# Drive ids are 20+ chars; give the fake tree realistic ones.
ROOT = "rootFolderId0000000000"
DSCID = "dscFolderId00000000000"
F0, F1, F2 = "fileReadme000000000000", "fileAcsv00000000000000", "fileBcsv00000000000000"

# a tiny tree: ROOT -> {folder DSC, file readme.txt}; DSC -> {a.csv, b.csv}
_PAGES = {
    ROOT: _entry(DSCID, "DSC", folder=True) + _entry(F0, "readme.txt", folder=False),
    DSCID: _entry(F1, "a.csv", folder=False) + _entry(F2, "b.csv", folder=False),
}


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://drive.google.com/drive/folders/16VQhcRbCHkzhH2cq8T5DwyhTUBj2BrO4", "16VQhcRbCHkzhH2cq8T5DwyhTUBj2BrO4"),
        ("https://drive.google.com/open?id=16VQhcRbCHkzhH2cq8T5DwyhTUBj2BrO4", "16VQhcRbCHkzhH2cq8T5DwyhTUBj2BrO4"),
        ("16VQhcRbCHkzhH2cq8T5DwyhTUBj2BrO4", "16VQhcRbCHkzhH2cq8T5DwyhTUBj2BrO4"),
    ],
)
def test_parse_drive_url(url, expected):
    assert parse_drive_url(url) == expected


def test_parse_drive_url_rejects_garbage():
    with pytest.raises(ValueError, match="Google Drive folder"):
        parse_drive_url("https://example.com/not-a-drive-link")


def test_make_source_routes_drive_vs_github():
    assert isinstance(make_source("https://drive.google.com/drive/folders/ABCDEFGHIJKLMNOPQRSTUVWX"), GoogleDriveSource)
    assert isinstance(make_source("yargerlab/Data"), GitHubSource)


@respx.mock
def test_list_files_walks_folder_tree():
    def responder(request):
        return httpx.Response(200, text=_PAGES[request.url.params["id"]])

    respx.get(url__startswith="https://drive.google.com/embeddedfolderview").mock(side_effect=responder)

    with GoogleDriveSource(ROOT, max_workers=2) as src:
        files = src.list_files()

    paths = sorted(f.path for f in files)
    assert paths == ["DSC/a.csv", "DSC/b.csv", "readme.txt"]
    a = next(f for f in files if f.path == "DSC/a.csv")
    assert a.top_dir == "DSC"
    assert a.download_url == f"https://drive.google.com/uc?export=download&id={F1}"


@respx.mock
def test_open_text_downloads_file():
    respx.get(url__startswith="https://drive.google.com/uc").mock(
        return_value=httpx.Response(200, headers={"content-type": "application/octet-stream"},
                                    text="wavenumber,intensity\n1000,5\n")
    )
    ref = FileRef(path="x.csv", download_url=f"https://drive.google.com/uc?export=download&id={F1}")
    with GoogleDriveSource(ROOT) as src:
        assert "wavenumber" in src.open_text(ref)
