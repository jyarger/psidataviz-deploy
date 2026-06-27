"""Visualize page: interactive overlay plot + metadata + marimo/Colab export."""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, no_update
from psidata.export import ExportItem, to_colab, to_marimo

from psidataviz_dash.plotting import build_figure
from psidataviz_dash.services import load_dataset

dash.register_page(__name__, path="/visualize", name="Visualize")


def layout(**_kwargs):
    return dmc.Stack(
        [
            dmc.Title("Visualize", order=2),
            html.Div(id="visualize-status"),
            dmc.Group(
                [
                    dmc.SegmentedControl(
                        id="x-axis",
                        value="temperature",
                        data=[{"value": "temperature", "label": "vs Temperature"},
                              {"value": "time", "label": "vs Time"}],
                    ),
                    dmc.Switch(id="exo-up", label="Exotherm up", checked=False),
                    dmc.Group(
                        [
                            dmc.Button("Open in marimo", id="dl-marimo", variant="light"),
                            dmc.Button("Open in Colab", id="dl-colab", variant="light"),
                        ],
                        gap="xs",
                    ),
                ],
                justify="space-between",
                align="center",
            ),
            dcc.Loading(dcc.Graph(id="dsc-graph"), type="dot"),
            dmc.Title("Dataset metadata", order=4),
            html.Div(id="meta-panel"),
            dcc.Download(id="download"),
        ],
        gap="md",
    )


@callback(
    Output("dsc-graph", "figure"),
    Output("meta-panel", "children"),
    Output("visualize-status", "children"),
    Input("selection", "data"),
    Input("x-axis", "value"),
    Input("exo-up", "checked"),
)
def render(selection, x_quantity, exo_up):
    if not selection:
        empty = build_figure([], x_quantity=x_quantity)
        return empty, None, dmc.Alert("Nothing selected — pick datasets on the Browse page.",
                                      color="yellow")
    datasets, errors = [], []
    for item in selection:
        try:
            datasets.append(load_dataset(item["name"], item["url"], technique=item.get("technique")))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{item['name']}: {exc}")

    figure = build_figure(datasets, x_quantity=x_quantity, exo_up=bool(exo_up))
    cards = [_metadata_card(ds) for ds in datasets]
    status = dmc.Alert("Some files failed to load: " + "; ".join(errors), color="red") if errors \
        else None
    return figure, dmc.SimpleGrid(cards, cols={"base": 1, "sm": 2, "lg": 3}), status


def _fmt_range(rng) -> str | None:
    if not rng:
        return None
    lo, hi = rng
    return f"{lo:.0f}–{hi:.0f} cm⁻¹"


def _metadata_card(ds) -> dmc.Paper:
    m = ds.metadata
    rows = [
        ("Sample", m.sample_name),
        ("Date", m.date.isoformat() if m.date else None),
        ("Instrument", m.instrument),
        ("Operator", m.operator),
        # DSC-specific (None for other techniques, so filtered out below)
        ("Sample mass", f"{m.sample_mass_mg} mg" if getattr(m, "sample_mass_mg", None) else None),
        ("Pan", getattr(m, "pan_type", None)),
        ("Exotherm", getattr(m, "exotherm_direction", None)),
        ("Segments", getattr(m, "n_segments", None)),
        # NMR-specific
        ("Nucleus", getattr(m, "nucleus", None)),
        ("Frequency", f"{m.frequency_mhz} MHz" if getattr(m, "frequency_mhz", None) else None),
        ("Solvent", getattr(m, "solvent", None)),
        ("Points", getattr(m, "npoints", None)),
        # FTIR / Raman
        ("Traces", getattr(m, "n_traces", None) or None),
        ("Range", _fmt_range(getattr(m, "wavenumber_range", None))),
    ]
    items = [
        dmc.Group([dmc.Text(f"{label}:", size="sm", fw=600, w=110),
                   dmc.Text(str(value), size="sm")], gap="xs")
        for label, value in rows if value not in (None, "")
    ]
    method_log = getattr(m, "method_log", []) or []
    if method_log:
        items.append(
            dmc.Spoiler(
                showLabel="Show method log", hideLabel="Hide", maxHeight=0,
                children=dmc.Stack([dmc.Text(step, size="xs", c="dimmed") for step in method_log],
                                   gap=2),
            )
        )
    return dmc.Paper(
        dmc.Stack([dmc.Text(ds.source.filename, fw=700, size="sm"), *items], gap=4),
        p="sm", withBorder=True, radius="md",
    )


def _export_items(selection) -> list[ExportItem]:
    return [ExportItem(name=item["name"], url=item["url"], technique=item.get("technique"))
            for item in selection]


@callback(
    Output("download", "data"),
    Input("dl-marimo", "n_clicks"),
    Input("dl-colab", "n_clicks"),
    State("selection", "data"),
    State("x-axis", "value"),
    prevent_initial_call=True,
)
def export(_m_clicks, _c_clicks, selection, x_quantity):
    if not selection:
        return no_update
    triggered = dash.ctx.triggered_id
    items = _export_items(selection)
    if triggered == "dl-marimo":
        return dcc.send_string(to_marimo(items, x_quantity=x_quantity), "psidata_export.py")
    if triggered == "dl-colab":
        data = to_colab(items, x_quantity=x_quantity)
        return dcc.send_bytes(lambda buffer: buffer.write(data), "psidata_export.ipynb")
    return no_update
