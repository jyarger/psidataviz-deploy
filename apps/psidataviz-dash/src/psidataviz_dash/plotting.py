"""Build interactive Plotly figures from parsed datasets.

Technique-agnostic where it can be; DSC conventions (exotherm direction, temperature vs time)
are handled explicitly. New techniques can add their own figure builders here later.
"""

from __future__ import annotations

import plotly.graph_objects as go
from psidata import Dataset

_PALETTE = (
    "#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed",
    "#db2777", "#0891b2", "#65a30d", "#ea580c", "#4f46e5",
)


def build_figure(datasets: list[Dataset], *, x_quantity: str = "temperature",
                 exo_up: bool = False) -> go.Figure:
    """Dispatch to the right figure builder based on the datasets' technique."""
    technique = datasets[0].technique if datasets else None
    if technique == "DSC":
        return build_dsc_figure(datasets, x_quantity=x_quantity, exo_up=exo_up)
    # NMR & FTIR plot with a reversed abscissa by convention; Raman does not.
    return build_spectrum_figure(datasets, reverse_x=technique in ("NMR", "FTIR"))


def build_spectrum_figure(datasets: list[Dataset], *, reverse_x: bool = False) -> go.Figure:
    """Overlay 1-D spectra (NMR / FTIR / Raman), labeling axes from each signal's own units."""
    fig = go.Figure()
    x_title, y_title = "x", "Intensity (a.u.)"
    color_idx = 0
    for ds in datasets:
        sample = ds.metadata.sample_name or (ds.source.filename or "spectrum")
        nucleus = getattr(ds.metadata, "nucleus", None)
        base_label = f"{sample} ({nucleus})" if nucleus else sample
        for sig in ds.signals:
            x_title, y_title = sig.x.title, sig.y.title
            name = base_label if sig.segment is None else f"{base_label} · {sig.segment}"
            fig.add_scatter(
                x=sig.frame[sig.x.label], y=sig.frame[sig.y.label], mode="lines", name=name,
                line={"color": _PALETTE[color_idx % len(_PALETTE)], "width": 1.2},
            )
            color_idx += 1
    fig.update_layout(
        template="plotly_dark",
        xaxis_title=x_title,
        yaxis_title=y_title,
        legend={"title": "Spectrum"},
        margin={"l": 60, "r": 20, "t": 30, "b": 50},
        height=560,
    )
    if reverse_x:
        fig.update_xaxes(autorange="reversed")
    if not fig.data:
        fig.add_annotation(text="No spectra in the current selection", showarrow=False,
                           font={"size": 16})
    return fig


def _x_column(signal, x_quantity: str) -> str:
    if x_quantity == "time":
        for col in signal.frame.columns:
            if "time" in col.lower():
                return col
    return signal.x.label


def build_dsc_figure(
    datasets: list[Dataset],
    *,
    x_quantity: str = "temperature",
    exo_up: bool = False,
) -> go.Figure:
    """Overlay heat-flow curves for the selected DSC datasets/segments."""
    fig = go.Figure()
    x_title = "Time (min)" if x_quantity == "time" else "Temperature (°C)"
    y_title = "Heat Flow"

    color_idx = 0
    for ds in datasets:
        sample = ds.metadata.sample_name or (ds.source.filename or "dataset")
        exo_dir = (getattr(ds.metadata, "exotherm_direction", None) or "").lower()
        flip = exo_up and exo_dir.startswith("down")
        for sig in ds.signals:
            df = sig.frame
            xcol = _x_column(sig, x_quantity)
            if xcol not in df.columns:
                continue
            y = df[sig.y.label]
            if flip:
                y = -y
            if sig.y.unit and sig.y.unit not in y_title:
                y_title = f"Heat Flow ({sig.y.unit})"
            fig.add_scatter(
                x=df[xcol],
                y=y,
                mode="lines",
                name=f"{sample} · {sig.segment}",
                line={"color": _PALETTE[color_idx % len(_PALETTE)], "width": 1.5},
                hovertemplate=f"{sample}<br>{xcol}: %{{x:.2f}}<br>%{{y:.4f}}<extra></extra>",
            )
            color_idx += 1

    if exo_up:
        y_title += "  ↑ exo"
    fig.update_layout(
        template="plotly_dark",
        xaxis_title=x_title,
        yaxis_title=y_title,
        legend={"title": "Dataset · segment", "orientation": "v"},
        margin={"l": 60, "r": 20, "t": 30, "b": 50},
        hovermode="closest",
        height=560,
    )
    if not fig.data:
        fig.add_annotation(text="No plottable signals in the current selection",
                           showarrow=False, font={"size": 16})
    return fig
