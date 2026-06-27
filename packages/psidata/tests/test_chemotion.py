from __future__ import annotations

import io
import zipfile

import httpx
import pytest
import respx

from psidata.sources.chemotion import (
    ChemotionSource,
    _tech_folder,
    parse_chemotion_url,
)

JDX = b"""##TITLE=test IR
##JCAMP-DX=4.24
##DATA TYPE=INFRARED SPECTRUM
##XUNITS=1/CM
##YUNITS=TRANSMITTANCE
##FIRSTX=400
##LASTX=402
##NPOINTS=3
##DELTAX=1
##XFACTOR=1
##YFACTOR=1
##XYDATA=(X++(Y..Y))
400 1.0 0.9 0.8
##END=
"""


@pytest.mark.parametrize(
    "url,kind,extra",
    [
        ("chemotion:3369", "molecule", {"id": 3369}),
        ("https://www.chemotion-repository.net/molecules/42", "molecule", {"id": 42}),
        ("https://www.chemotion-repository.net/x?id=7", "molecule", {"id": 7}),
        ("10.14272/PMQHVQYSNNTEKV-UHFFFAOYSA-N.1", "inchikey", {"inchikey": "PMQHVQYSNNTEKV-UHFFFAOYSA-N"}),
        ("https://www.chemotion-repository.net/home", "browse", {}),
    ],
)
def test_parse_chemotion_url(url, kind, extra):
    t = parse_chemotion_url(url)
    assert t["kind"] == kind
    for k, v in extra.items():
        assert t[k] == v


def test_parse_chemotion_url_rejects_other():
    with pytest.raises(ValueError):
        parse_chemotion_url("https://github.com/x/y")


def test_tech_folder_maps_analysis_names():
    assert _tech_folder("1H NMR") == "NMR"
    assert _tech_folder("13C NMR") == "NMR"
    assert _tech_folder("Mass") == "Mass Spec"
    assert _tech_folder("IR") == "FTIR"
    assert _tech_folder("Weird Analysis") == "Weird Analysis"


def _bagit_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bagit.txt", "BagIt-Version: 1.0\n")
        zf.writestr("data/sample_1/analysis_111/dataset_1/test.edit.jdx", JDX)
        zf.writestr("data/sample_1/analysis_111/dataset_1/test.edit.png", b"\x89PNG")
    return buf.getvalue()


@respx.mock
def test_chemotion_source_lists_and_opens():
    zip_url = "https://www.chemotion-repository.net/zip/samples/publication_Sample_1.zip"
    detail = {
        "molecule": {"id": 42, "sum_formular": "C2H6O"},
        "published_samples": [{
            "short_label": "TST-1",
            "zip_download_url": zip_url,
            "container": {"children": [{"children": [{"id": 111, "name": "IR"}]}]},
        }],
    }
    respx.get("https://www.chemotion-repository.net/api/v1/public/molecule?id=42").mock(
        return_value=httpx.Response(200, json=detail)
    )
    respx.get(zip_url).mock(return_value=httpx.Response(200, content=_bagit_zip()))

    with ChemotionSource("chemotion:42") as src:
        refs = src.list_files()
        assert len(refs) == 1
        ref = refs[0]
        assert ref.path == "FTIR/TST-1 IR.jdx"  # technique folder + sample label + analysis name
        assert ref.download_url == f"{zip_url}!data/sample_1/analysis_111/dataset_1/test.edit.jdx"
        assert src.open_bytes(ref) == JDX
