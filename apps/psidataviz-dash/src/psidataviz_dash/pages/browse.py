"""Browse page: pick a technique, see its datasets, select some to visualize."""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dash_table, dcc, html, no_update
from psidata.sources.records import IMAGE

from psidataviz_dash.services import scan_repo

dash.register_page(__name__, path="/browse", name="Browse")

_COLUMNS = [
    {"name": "Date", "id": "date"},
    {"name": "Sample / description", "id": "description"},
    {"name": "Formats", "id": "formats"},
]


def layout(**_kwargs):
    return dmc.Stack(
        [
            dmc.Title("Browse datasets", order=2),
            html.Div(id="browse-status"),
            dmc.Group(
                [
                    dmc.Select(id="technique-select", label="Instrument / method",
                               placeholder="scan a repo first", style={"minWidth": 240}),
                    dmc.Button("Visualize selected →", id="visualize-btn", mt=25),
                ],
                align="flex-end",
            ),
            dcc.Loading(
                dash_table.DataTable(
                    id="dataset-table",
                    columns=_COLUMNS,
                    data=[],
                    row_selectable="multi",
                    page_size=15,
                    sort_action="native",
                    filter_action="native",
                    style_table={"overflowX": "auto"},
                    style_cell={"fontFamily": "system-ui", "fontSize": 13, "textAlign": "left",
                                "padding": "6px 10px", "maxWidth": 420, "whiteSpace": "normal",
                                "backgroundColor": "#1f2128", "color": "#e6e6e6",
                                "border": "1px solid #2c2e33"},
                    style_header={"fontWeight": 700, "backgroundColor": "#2c2e33",
                                  "color": "#e6e6e6", "border": "1px solid #2c2e33"},
                    style_data_conditional=[{"if": {"state": "selected"},
                                             "backgroundColor": "#1c7ed633",
                                             "border": "1px solid #1c7ed6"}],
                ),
                type="dot",
            ),
            dcc.Location(id="browse-redirect", refresh=True),
        ],
        gap="md",
    )


@callback(
    Output("technique-select", "data"),
    Output("technique-select", "value"),
    Output("browse-status", "children"),
    Input("repo-url", "data"),
)
def populate_techniques(url):
    if not url:
        return [], None, dmc.Alert("No repository scanned yet — go to Home and scan one.",
                                   color="yellow")
    catalog = scan_repo(url)
    groups = catalog.record_groups()
    options = [
        {"value": tech, "label": f"{tech} ({sum(r.supported for r in recs)} datasets)"}
        for tech, recs in groups.items()
        if any(r.supported for r in recs)
    ]
    if not options:
        return [], None, dmc.Alert("No datasets with a matching reader were found.", color="yellow")
    default = "DSC" if any(o["value"] == "DSC" for o in options) else options[0]["value"]
    return options, default, dmc.Text(f"Source: {catalog.source_label}", size="sm", c="dimmed")


@callback(
    Output("dataset-table", "data"),
    Input("repo-url", "data"),
    Input("technique-select", "value"),
)
def fill_table(url, technique):
    if not url or not technique:
        return []
    catalog = scan_repo(url)
    rows = []
    for record in catalog.record_groups().get(technique, []):
        if not record.supported:          # needs at least one parseable data format
            continue
        data_exts = sorted({v.ext for v in record.data_variants})
        extras = []
        if record.sidecars:
            extras.append("params")
        if any(v.info.role == IMAGE for v in record.variants):
            extras.append("img")
        formats = ", ".join(data_exts) + (f"  (+{', '.join(extras)})" if extras else "")
        rows.append({
            "date": record.parsed.date.isoformat() if record.parsed.date else "",
            "description": record.parsed.description,
            "formats": formats,
            "name": record.primary.file.name,            # the variant we'll actually parse
            "download_url": record.primary.file.download_url,
        })
    rows.sort(key=lambda r: r["date"])
    return rows


@callback(
    Output("selection", "data"),
    Output("browse-redirect", "href"),
    Output("browse-status", "children", allow_duplicate=True),
    Input("visualize-btn", "n_clicks"),
    State("dataset-table", "data"),
    State("dataset-table", "selected_rows"),
    State("technique-select", "value"),
    prevent_initial_call=True,
)
def go_visualize(_clicks, data, selected_rows, technique):
    if not selected_rows:
        return no_update, no_update, dmc.Alert("Select one or more rows first.", color="yellow")
    selection = [
        {"name": data[i]["name"], "url": data[i]["download_url"], "technique": technique}
        for i in selected_rows
    ]
    return selection, "/visualize", no_update
