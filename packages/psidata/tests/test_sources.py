from __future__ import annotations

import httpx
import pytest
import respx

from psidata.sources import GitHubSource, parse_repo_url, scan
from psidata.sources.base import DataSource, FileRef


# --- URL parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url,owner,repo,ref,subpath",
    [
        ("yargerlab/Data", "yargerlab", "Data", None, None),
        ("https://github.com/yargerlab/Data", "yargerlab", "Data", None, None),
        ("https://github.com/yargerlab/Data.git", "yargerlab", "Data", None, None),
        ("https://github.com/yargerlab/Data/tree/main", "yargerlab", "Data", "main", None),
        ("https://github.com/yargerlab/Data/tree/main/DSC", "yargerlab", "Data", "main", "DSC"),
    ],
)
def test_parse_repo_url(url, owner, repo, ref, subpath):
    r = parse_repo_url(url)
    assert (r.owner, r.repo, r.ref, r.subpath) == (owner, repo, ref, subpath)


def test_parse_repo_url_rejects_garbage():
    with pytest.raises(ValueError):
        parse_repo_url("not a url")


# --- GitHubSource over a mocked API -----------------------------------------------------------
def _mock_tree():
    return {
        "tree": [
            {"path": "DSC", "type": "tree"},
            {"path": "DSC/2023_06_14_Indium_wire_std.txt", "type": "blob", "size": 146454},
            {"path": "DSC/2023_06_14_Indium_wire_std.tri", "type": "blob", "size": 1136465},
            {"path": "FTIR/2024_01_02_sample.csv", "type": "blob", "size": 2048},
            {"path": "README.md", "type": "blob", "size": 100},
        ]
    }


@respx.mock
def test_github_source_lists_and_opens():
    respx.get("https://api.github.com/repos/yargerlab/Data").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"})
    )
    respx.get("https://api.github.com/repos/yargerlab/Data/git/trees/main").mock(
        return_value=httpx.Response(200, json=_mock_tree())
    )
    raw = "https://raw.githubusercontent.com/yargerlab/Data/main/DSC/2023_06_14_Indium_wire_std.txt"
    respx.get(raw).mock(return_value=httpx.Response(200, text="Filename\tx\n[step]\n"))

    with GitHubSource("yargerlab/Data") as src:
        files = src.list_files()
        names = {f.name for f in files}
        assert "2023_06_14_Indium_wire_std.txt" in names
        assert "README.md" in names
        assert all(f.path != "DSC" for f in files)  # tree nodes skipped

        dsc_txt = next(f for f in files if f.name.endswith("Indium_wire_std.txt"))
        assert dsc_txt.top_dir == "DSC"
        assert dsc_txt.download_url == raw
        assert "[step]" in src.open_text(dsc_txt)


@respx.mock
def test_github_source_respects_subpath():
    respx.get("https://api.github.com/repos/yargerlab/Data/git/trees/main").mock(
        return_value=httpx.Response(200, json=_mock_tree())
    )
    with GitHubSource("https://github.com/yargerlab/Data/tree/main/DSC") as src:
        files = src.list_files()
        assert files and all(f.path.startswith("DSC/") for f in files)


# --- Catalog scanning (pure, no network) ------------------------------------------------------
class FakeSource(DataSource):
    label = "fake"

    def __init__(self, paths):
        self._refs = [FileRef(path=p, size=10) for p in paths]

    def list_files(self):
        return self._refs

    def open_text(self, ref):
        return ""

    def open_bytes(self, ref):
        return b""


def test_catalog_groups_and_flags_supported():
    src = FakeSource([
        "DSC/2023_06_14_Indium_wire_std.txt",   # supported (DSC reader, .txt)
        "DSC/2023_06_14_Indium_wire_std.tri",   # unsupported (.tri not handled)
        "DSC/2023_04_21_CBD.xls",               # supported via the generic spreadsheet reader
        "FTIR/2024_01_02_sample.csv",           # supported: FTIR reader claims .csv in FTIR/
        "README.md",                            # root group
    ])
    cat = scan(src)

    groups = cat.groups()
    assert set(groups) == {"DSC", "FTIR", "(root)"}

    by_name = {e.file.name: e for e in cat.entries}
    txt = by_name["2023_06_14_Indium_wire_std.txt"]
    assert txt.supported and txt.reader_name == "dsc_trios"
    assert txt.parsed.description == "Indium wire std"
    assert not by_name["2023_06_14_Indium_wire_std.tri"].supported
    ftir = by_name["2024_01_02_sample.csv"]
    assert ftir.supported and ftir.reader_name == "ftir_text"

    summary = cat.summary()
    assert summary["n_files"] == 5
    assert summary["n_supported"] == 3  # DSC .txt + FTIR .csv + the .xls (generic spreadsheet reader)
    assert summary["groups"]["DSC"]["n_supported"] == 2  # the .txt and the .xls
    assert summary["groups"]["FTIR"]["n_supported"] == 1


def test_guess_compound_from_filename():
    from psidata.sources.catalog import guess_compound

    assert guess_compound("2022_11_17_CBD_Xtal_532nm_DePol.csv") == "CBD"
    assert guess_compound("Acetaminophen_DSC.txt") == "Acetaminophen"
    assert guess_compound("Ethane_DFT_b3lyp.log") == "Ethane"      # method tokens stripped
    assert guess_compound("Terpyridine_FeCl3_MS.zip") == "Terpyridine"
    assert guess_compound("532nm_only.csv") == ""                   # no real word


def test_compound_for_sample_vs_instrument_organized():
    from psidata.sources.catalog import compound_for

    # instrument-organized (Raman folder has a reader) -> compound from the filename
    assert compound_for("Raman", "Aspirin_532nm") == "Aspirin"
    # sample-organized (top folder is the compound, no reader for it) -> the folder
    assert compound_for("Cannabidiol/sub", "x_1H_400MHz") == "Cannabidiol"


def test_detect_organization_classifies_layout():
    from psidata.sources.base import FileRef
    from psidata.sources.catalog import build_entry, detect_organization

    def ents(paths):
        return [build_entry(FileRef(path=p, size=1)) for p in paths]

    tech = ents(["Raman/a.csv", "NMR/b.jdx", "XRD/c.xy", "README.md"])  # README ignored
    assert detect_organization(tech)["kind"] == "technique"
    samp = ents(["Aspirin/x_raman.csv", "Aspirin/y_1H_nmr.jdx", "CBD/z_raman.csv"])
    assert detect_organization(samp)["kind"] == "sample"
    un = ents(["a.bin", "b.dat", "c.qqq"])  # root files, no technique/compound
    assert detect_organization(un)["kind"] == "unstructured"
