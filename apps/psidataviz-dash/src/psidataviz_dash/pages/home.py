"""Home page: point at a public GitHub repo and scan it into a catalog."""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, no_update

from psidataviz_dash.services import scan_repo

dash.register_page(__name__, path="/", name="Home")

DEFAULT_REPO = "https://github.com/yargerlab/Data"


def layout(**_kwargs):
    return dmc.Stack(
        [
            dmc.Title("Point at a data repository", order=2),
            dmc.Text(
                "Paste a public GitHub repo that stores molecular-science data in per-instrument "
                "folders (e.g. DSC/, FTIR/, NMR/). PsiData scans it and summarizes what it finds.",
                c="dimmed",
            ),
            dmc.Group(
                [
                    dmc.TextInput(
                        id="repo-input",
                        value=DEFAULT_REPO,
                        placeholder="owner/repo or https://github.com/owner/repo",
                        label="GitHub repository",
                        style={"flex": 1, "minWidth": 360},
                    ),
                    dmc.Button("Scan repository", id="scan-btn", mt=25),
                ],
                align="flex-end",
            ),
            dcc.Loading(dash.html.Div(id="scan-output"), type="dot"),
        ],
        gap="md",
    )


@callback(
    Output("repo-url", "data"),
    Output("scan-output", "children"),
    Input("scan-btn", "n_clicks"),
    State("repo-input", "value"),
    prevent_initial_call=True,
)
def on_scan(_clicks, url):
    if not url or not url.strip():
        return no_update, dmc.Alert("Please enter a repository URL.", color="yellow")
    try:
        catalog = scan_repo(url.strip())
    except Exception as exc:  # noqa: BLE001 - surface any failure to the user
        return no_update, dmc.Alert(f"Could not scan {url!r}: {exc}", color="red",
                                    title="Scan failed")

    summary = catalog.summary()
    # Per-technique dataset (record) counts — files grouped into one dataset per base name.
    rec_groups = catalog.record_groups()
    tech_counts = {
        tech: (sum(r.supported for r in recs), sum(r.is_data_record for r in recs))
        for tech, recs in rec_groups.items()
    }
    badges = [
        dmc.Badge(
            f"{tech} · {viz}/{data} datasets",
            variant="filled" if viz else "light",
            color="blue" if viz else "gray",
            size="lg",
        )
        for tech, (viz, data) in sorted(tech_counts.items(), key=lambda kv: (-kv[1][0], kv[0]))
        if data
    ]
    body = dmc.Stack(
        [
            dmc.Text(
                f"Found {summary['n_files']} files → grouped into {summary['n_data_records']} "
                f"datasets across {len(tech_counts)} instruments — "
                f"{summary['n_supported_records']} visualizable with current readers.",
                fw=600,
            ),
            dmc.Text(
                "Files sharing a base name across formats (e.g. .csv/.txt/.tri/.xls) count as one "
                "dataset; sidecar files (e.g. Raman _spec.txt) are not treated as data.",
                size="xs", c="dimmed",
            ),
            dmc.Text("Instruments (visualizable / total datasets):", size="sm", c="dimmed"),
            dmc.Group(badges, gap="xs"),
            dcc.Link(dmc.Button("Browse datasets →", mt="sm"), href="/browse"),
        ],
        gap="xs",
    )
    return url.strip(), dmc.Paper(body, p="md", withBorder=True, radius="md", mt="sm")
