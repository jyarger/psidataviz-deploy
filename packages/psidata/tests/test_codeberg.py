from __future__ import annotations

import httpx
import respx

from psidata.sources import (
    CodebergSource,
    GitHubSource,
    GoogleDriveSource,
    build_entry,
    make_source,
)
from psidata.sources.base import FileRef
from psidata.sources.catalog import infer_technique


def test_make_source_routes_codeberg():
    assert isinstance(make_source("https://codeberg.org/jyarger/PsiData"), CodebergSource)
    assert isinstance(make_source("https://drive.google.com/drive/folders/ABCDEFGHIJKLMNOPQRSTUVWX"),
                      GoogleDriveSource)
    assert isinstance(make_source("yargerlab/Data"), GitHubSource)


@respx.mock
def test_codeberg_lists_files_and_raw_urls():
    respx.get("https://codeberg.org/api/v1/repos/o/r").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"}))
    tree = {"tree": [
        {"path": "Aspirin", "type": "tree"},
        {"path": "Aspirin/2023_Aspirin_BrukerFTIR.zip", "type": "blob", "size": 9},
    ]}
    respx.get(url__startswith="https://codeberg.org/api/v1/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(200, json=tree))
    with CodebergSource("https://codeberg.org/o/r") as src:
        files = src.list_files()
    assert [f.path for f in files] == ["Aspirin/2023_Aspirin_BrukerFTIR.zip"]
    assert files[0].download_url == "https://codeberg.org/o/r/raw/branch/main/Aspirin/2023_Aspirin_BrukerFTIR.zip"


def test_infer_technique_from_filename():
    assert infer_technique("2023_04_20_Acetylsalicylic_Acid_BrukerFTIR.zip") == "FTIR"
    assert infer_technique("2025_10_30_Aspirin_MDSC.zip") == "DSC"
    assert infer_technique("2026_05_10_Aspirin_CDCl3_TMS_Bruker500.zip") == "NMR"
    assert infer_technique("just_some_data.csv") is None


def test_sample_organized_folder_infers_technique():
    # top folder is a compound (no reader) -> technique comes from the filename, so a zipped
    # FTIR dataset is recognized as supported
    entry = build_entry(FileRef(path="Aspirin/2023_Aspirin_BrukerFTIR.zip", size=1))
    assert entry.technique == "FTIR" and entry.supported
    # an instrument-organized folder is unaffected
    assert build_entry(FileRef(path="DSC/2026_run.csv", size=1)).technique == "DSC"
