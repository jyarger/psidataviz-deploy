"""Dash application factory + entrypoint.

The app is a thin shell: a header with navigation, two session-scoped ``dcc.Store``s that carry
the current repo URL and dataset selection across pages, and a page container. All real work lives
in :mod:`psidataviz_dash.services`, :mod:`psidataviz_dash.plotting`, and the core library.
"""

from __future__ import annotations

import os

import dash
import dash_mantine_components as dmc
from dash import Dash, dcc

BRAND = "ΨDataViz"  # display wordmark (spelled "PsiDataViz")
TAGLINE = "Scientific Data Visualization"

# Inline Ψ favicon (no asset file needed).
_FAVICON = (
    "data:image/svg+xml,"
    "<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22>"
    "<text x=%2250%22 y=%2278%22 font-size=%2284%22 text-anchor=%22middle%22 "
    "fill=%22%231c7ed6%22 font-family=%22serif%22>%CE%A8</text></svg>"
)
_INDEX = """<!DOCTYPE html>
<html>
<head>{%metas%}<title>{%title%}</title>
<link rel="icon" href="__FAVICON__">{%css%}</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>""".replace("__FAVICON__", _FAVICON)

_NAV = [("Home", "/"), ("Browse", "/browse"), ("Visualize", "/visualize")]


def _header() -> dmc.Paper:
    links = [
        dcc.Link(
            label,
            href=href,
            style={"textDecoration": "none", "color": "#1c7ed6", "fontWeight": 600,
                   "padding": "4px 10px"},
        )
        for label, href in _NAV
    ]
    return dmc.Paper(
        dmc.Group(
            [
                dmc.Stack(
                    [
                        dmc.Title(
                            [dmc.Text("Ψ", span=True, inherit=True, c="blue.4"), "DataViz"],
                            order=2, m=0,
                        ),
                        dmc.Text(TAGLINE, size="xs", c="dimmed"),
                    ],
                    gap=0,
                ),
                dmc.Group(links, gap="xs"),
            ],
            justify="space-between",
            align="center",
        ),
        p="md",
        shadow="xs",
        radius=0,
        withBorder=True,
    )


def create_app() -> Dash:
    app = Dash(
        __name__,
        use_pages=True,
        suppress_callback_exceptions=True,
        title=BRAND,
        update_title=None,
    )
    app.index_string = _INDEX
    app.layout = dmc.MantineProvider(
        forceColorScheme="dark",
        children=[
            dcc.Store(id="repo-url", storage_type="session"),
            dcc.Store(id="selection", storage_type="session"),
            _header(),
            dmc.Container(dash.page_container, size="xl", py="lg"),
        ],
    )
    return app


app = create_app()
server = app.server  # WSGI entrypoint for gunicorn


def main() -> None:
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8050")),
        debug=os.environ.get("PSIDATA_DEBUG", "") in ("1", "true", "True"),
    )


if __name__ == "__main__":
    main()
