"""App-layer tests that need no network: figure building, export artifacts, app wiring."""

from __future__ import annotations

import nbformat
from psidata import Candidate, read
from psidata.export import ExportItem, to_colab, to_marimo


def _dataset(dsc_txt):
    return read(Candidate(filename="2023_06_14_Indium_wire_std.txt", text=dsc_txt,
                          uri="https://example/DSC/run.txt"))


def test_build_dsc_figure_overlays_segments(dsc_txt):
    from psidataviz_dash.plotting import build_dsc_figure

    ds = _dataset(dsc_txt)
    fig = build_dsc_figure([ds, ds], x_quantity="temperature")
    assert len(fig.data) == 4  # 2 datasets x 2 segments
    assert "Temperature" in fig.layout.xaxis.title.text


def test_exo_up_flips_sign(dsc_txt):
    from psidataviz_dash.plotting import build_dsc_figure

    ds = _dataset(dsc_txt)  # exotherm direction = Down
    normal = build_dsc_figure([ds], exo_up=False).data[0].y
    flipped = build_dsc_figure([ds], exo_up=True).data[0].y
    assert (flipped == -normal).all()


def test_empty_selection_yields_placeholder():
    from psidataviz_dash.plotting import build_dsc_figure

    fig = build_dsc_figure([], x_quantity="temperature")
    assert not fig.data
    assert fig.layout.annotations  # "no plottable signals" note


def test_export_marimo_is_valid_python():
    items = [ExportItem("run.txt", "https://example/run.txt")]
    src = to_marimo(items, x_quantity="time")
    compile(src, "psidata_export.py", "exec")  # raises SyntaxError if malformed
    assert "marimo" in src and "https://example/run.txt" in src


def test_export_colab_is_valid_notebook():
    items = [ExportItem("run.txt", "https://example/run.txt")]
    nb = nbformat.reads(to_colab(items).decode("utf-8"), as_version=4)
    assert nb.cells[1].source.startswith("!pip install")
    assert any("psidata" in c.source for c in nb.cells)


def test_app_factory_registers_three_pages():
    import dash

    from psidataviz_dash.server import create_app

    create_app()
    paths = {p["path"] for p in dash.page_registry.values()}
    assert {"/", "/browse", "/visualize"} <= paths
