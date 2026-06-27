from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from psidata_backend.main import app
from psidata_backend.services import _listing_cache

client = TestClient(app)


def test_health_lists_readers():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    techniques = {r["technique"] for r in body["readers"]}
    assert {"DSC", "NMR", "FTIR", "Raman"} <= techniques


@respx.mock
def test_dataset_endpoint_serves_downsampled_points():
    raw = "https://raw.githubusercontent.com/o/r/main/Raman/2026_01_01_x.csv"
    respx.get(raw).mock(return_value=httpx.Response(200, text="10,100\n9,200\n8,150\n"))
    resp = client.get("/api/dataset", params={"url": raw, "name": "2026_01_01_x.csv",
                                              "technique": "Raman"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["technique"] == "Raman"
    assert data["signals"][0]["x"]["label"] == "Raman shift"
    assert data["signals"][0]["points"][0] == [10.0, 100.0]


@respx.mock
def test_scan_endpoint_summarizes_records():
    _listing_cache.clear()
    respx.get("https://api.github.com/repos/o/r").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"}))
    tree = {"tree": [
        {"path": "DSC/2026_01_01_run.csv", "type": "blob", "size": 10},
        {"path": "DSC/2026_01_01_run.tri", "type": "blob", "size": 10},
    ]}
    respx.get("https://api.github.com/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(200, json=tree))
    body = client.get("/api/scan", params={"url": "o/r"}).json()
    assert body["n_records"] == 1                          # csv + tri -> one dataset
    assert any(t["technique"] == "DSC" for t in body["techniques"])


@respx.mock
def test_convert_endpoint_returns_csdm_download():
    raw = "https://raw.githubusercontent.com/o/r/main/Raman/2026_01_01_x.csv"
    respx.get(raw).mock(return_value=httpx.Response(200, text="10,100\n9,200\n8,150\n"))
    resp = client.get("/api/convert", params={"url": raw, "name": "2026_01_01_x.csv",
                                              "technique": "Raman", "fmt": "csdf"})
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    import json
    assert json.loads(resp.content)["csdm"]["version"] == "1.0"


@respx.mock
def test_convert_endpoint_csv_download():
    raw = "https://raw.githubusercontent.com/o/r/main/Raman/2026_01_01_x.csv"
    respx.get(raw).mock(return_value=httpx.Response(200, text="10,100\n9,200\n8,150\n"))
    resp = client.get("/api/convert", params={"url": raw, "name": "2026_01_01_x.csv",
                                              "technique": "Raman", "fmt": "csv"})
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].endswith('.csv"')
    assert b"signal" in resp.content  # tidy CSV header


def test_convert_endpoint_rejects_unknown_format():
    assert client.get("/api/convert", params={"url": "x", "name": "y.csv", "fmt": "bogus"}
                      ).status_code == 400


def test_dataset_endpoint_reports_errors():
    # missing required params -> 422 from FastAPI
    assert client.get("/api/dataset").status_code == 422


@respx.mock
def test_catalog_endpoint_returns_summary_and_records():
    _listing_cache.clear()
    respx.get("https://api.github.com/repos/o/r").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"}))
    tree = {"tree": [
        {"path": "Raman/2026_01_01_x.csv", "type": "blob", "size": 10},
        {"path": "DSC/2026_01_01_run.csv", "type": "blob", "size": 10},
    ]}
    respx.get("https://api.github.com/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(200, json=tree))
    body = client.get("/api/catalog", params={"url": "o/r"}).json()
    assert "records" in body and isinstance(body["records"], list)
    techniques = {r["technique"] for r in body["records"]}
    assert {"Raman", "DSC"} <= techniques
    assert all("url" in r and "name" in r for r in body["records"])


def test_dataset_json_downsamples_and_logscales_image():
    import numpy as np
    from psidata import Axis, Dataset, Image2D, Metadata, SourceInfo

    from psidata_backend import services

    arr = np.zeros((500, 600), dtype="float32")
    arr[100, 100] = 1e6
    ds = Dataset(
        technique="XRD", source=SourceInfo(filename="big.edf"), metadata=Metadata(),
        images=[Image2D(name="img", data=arr,
                        x=Axis(label="x", unit="px"), y=Axis(label="y", unit="px"),
                        z=Axis(label="Intensity", unit="counts"))],
    )
    img = services.dataset_json(ds)["images"][0]
    assert img["shape"] == [500, 600]
    assert len(img["values"]) <= 240 and len(img["values"][0]) <= 240   # downsampled
    assert img["z"]["scale"] == "log1p"
    assert max(max(row) for row in img["values"]) > 0


@respx.mock
def test_scan_diagnostics_reports_unread_formats():
    _listing_cache.clear()
    respx.get("https://api.github.com/repos/o/r").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"}))
    tree = {"tree": [
        {"path": "Raman/2026_01_01_x.csv", "type": "blob", "size": 10},  # supported
        {"path": "Mystery/scan.spe", "type": "blob", "size": 10},        # data file, no reader
    ]}
    respx.get("https://api.github.com/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(200, json=tree))
    diag = client.get("/api/scan", params={"url": "o/r"}).json()["diagnostics"]
    assert diag["coverage"] == 50.0
    assert diag["n_supported"] == 1 and diag["n_unsupported"] == 1
    assert ".spe" in [f["ext"] for f in diag["unread_formats"]]


@respx.mock
def test_diagnostics_annotates_known_formats():
    _listing_cache.clear()
    respx.get("https://api.github.com/repos/o/r").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"}))
    tree = {"tree": [{"path": "DSC/run.tri", "type": "blob", "size": 10}]}  # Trios binary, no reader
    respx.get("https://api.github.com/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(200, json=tree))
    diag = client.get("/api/scan", params={"url": "o/r"}).json()["diagnostics"]
    tri = next(f for f in diag["unread_formats"] if f["ext"] == ".tri")
    assert "Trios" in tri["note"] and "export" in tri["hint"].lower()


@respx.mock
def test_diagnostics_unread_items_give_per_dataset_reasons():
    _listing_cache.clear()
    respx.get("https://api.github.com/repos/o/r").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"}))
    tree = {"tree": [
        {"path": "DSC/2026_run.tri", "type": "blob", "size": 10},            # known binary -> note + hint
        {"path": "Ellipsometry/2026_film.zip", "type": "blob", "size": 10},  # whole technique unread
    ]}
    respx.get("https://api.github.com/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(200, json=tree))
    items = client.get("/api/scan", params={"url": "o/r"}).json()["diagnostics"]["unread_items"]
    by_tech = {it["technique"]: it for it in items}
    assert "Trios" in by_tech["DSC"]["reason"] and by_tech["DSC"]["hint"]
    assert by_tech["Ellipsometry"]["reason"] == "No reader for Ellipsometry data yet"
    assert by_tech["Ellipsometry"]["formats"] == [".zip"]


@respx.mock
def test_dataset_merges_raman_spec_sidecar():
    raw = "https://raw.githubusercontent.com/o/r/main/Raman/x.csv"
    spec = "https://raw.githubusercontent.com/o/r/main/Raman/x_spec.txt"
    respx.get(raw).mock(return_value=httpx.Response(200, text="10,100\n9,200\n8,150\n"))
    respx.get(spec).mock(return_value=httpx.Response(200, text="Green\n1.3mW\nAndor750 (3)\nDepolarized\n"))
    md = client.get("/api/dataset", params={"url": raw, "name": "x.csv", "technique": "Raman",
                                            "sidecar_url": spec}).json()["metadata"]
    assert md["laser"] == "Green" and md["laser_power_mw"] == 1.3
    assert md["spectrometer"] == "Andor750 (3)" and md["polarization"] == "Depolarized"


def test_upload_endpoint_scans_and_loads_local_files():
    # a dropped "folder": an XRD .xy at a folder path
    xy = b"10 100\n20 350\n30 80\n40 1200\n50 60\n"
    res = client.post("/api/upload", files=[("files", ("XRD/pattern.xy", xy, "text/plain"))])
    assert res.status_code == 200
    body = res.json()
    assert body["url"].startswith("upload://")
    rec = next(r for r in body["records"] if r["technique"] == "XRD")
    assert rec["url"].startswith("upload://")
    # the uploaded file loads back through the normal dataset endpoint
    ds = client.get("/api/dataset", params={"url": rec["url"], "name": rec["name"],
                                            "technique": "XRD"}).json()
    assert ds["reader"] == "xrd_text" and ds["signals"]


def test_upload_expands_a_single_dropped_zip():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("XRD/a.xy", "10 1\n20 2\n30 3\n")
    res = client.post("/api/upload", files=[("files", ("bundle.zip", buf.getvalue(), "application/zip"))])
    assert res.status_code == 200
    # the zip is expanded -> the inner .xy becomes a record, not a single .zip record
    assert any(r["name"] == "a.xy" for r in res.json()["records"])


@respx.mock
def test_scan_keyword_filter_limits_files():
    _listing_cache.clear()
    respx.get("https://api.github.com/repos/o/r").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"}))
    tree = {"tree": [
        {"path": "Raman/aspirin_532nm.csv", "type": "blob", "size": 10},
        {"path": "Raman/caffeine_532nm.csv", "type": "blob", "size": 10},
        {"path": "NMR/aspirin_1H.jdx", "type": "blob", "size": 10},
    ]}
    respx.get("https://api.github.com/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(200, json=tree))
    body = client.get("/api/scan", params={"url": "o/r", "filter": "aspirin"}).json()
    # only the two aspirin files survive the keyword filter
    assert body["n_files"] == 2
    techs = {t["technique"] for t in body["techniques"]}
    assert techs == {"Raman", "NMR"}
