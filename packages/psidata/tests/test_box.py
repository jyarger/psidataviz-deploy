from __future__ import annotations

import httpx
import respx

from psidata.sources import BoxSource, GitHubSource, make_source
from psidata.sources.box import _current_folder_id, _items, parse_box_url


def _page(current: int, items: list[dict]) -> str:
    import json

    blob = json.dumps({"shared-item": {"items": items}})
    return f'<html><script>Box.postStreamData = {blob};</script>' \
           f'<div data-current="x">"currentFolderID":{current}</div></html>'


def test_parse_box_url_and_routing():
    assert parse_box_url("https://app.box.com/s/ABC123") == "ABC123"
    assert isinstance(make_source("https://app.box.com/s/ABC123"), BoxSource)
    assert isinstance(make_source("yargerlab/Data"), GitHubSource)


def test_items_filters_breadcrumbs():
    items = [
        {"typedID": "d_200", "type": "folder", "id": 200, "name": "NMR", "parentFolderID": 100},
        {"typedID": "f_300", "type": "file", "id": 300, "name": "a.jdx", "parentFolderID": 100,
         "itemSize": 42},
        {"typedID": "d_1", "type": "folder", "id": 1, "name": "All Files", "parentFolderID": 0},  # crumb
    ]
    html = _page(100, items)
    assert _current_folder_id(html) == 100
    got = _items(html, 100)
    assert {(i["name"], i["type"]) for i in got} == {("NMR", "folder"), ("a.jdx", "file")}


@respx.mock
def test_box_lists_recursively_and_builds_download_urls():
    sn = "ABC123"
    root = _page(100, [
        {"typedID": "d_200", "type": "folder", "id": 200, "name": "Aspirin", "parentFolderID": 100},
        {"typedID": "d_9", "type": "folder", "id": 9, "name": "crumb", "parentFolderID": 0},
    ])
    sub = _page(200, [
        {"typedID": "f_300", "type": "file", "id": 300, "name": "run_DSC.csv", "parentFolderID": 200,
         "itemSize": 10},
    ])
    respx.get(f"https://app.box.com/s/{sn}").mock(return_value=httpx.Response(200, text=root))
    respx.get(f"https://app.box.com/s/{sn}/folder/200").mock(return_value=httpx.Response(200, text=sub))

    with BoxSource(f"https://app.box.com/s/{sn}") as src:
        files = src.list_files()
    assert [f.path for f in files] == ["Aspirin/run_DSC.csv"]
    assert "rm=box_download_shared_file" in files[0].download_url
    assert "file_id=f_300" in files[0].download_url and f"shared_name={sn}" in files[0].download_url
