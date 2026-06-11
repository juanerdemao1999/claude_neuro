from __future__ import annotations

from typing import Iterable

import matplotlib
from matplotlib.figure import Figure
import numpy as np
import pandas as pd
import scienceplots  # noqa: F401
import seaborn as sns
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

from .models import AnalysisResult


PLOT_STYLE = ["science", "nature", "no-latex"]
PLOT_CONTEXT = "paper"
PLOT_PALETTE = "colorblind"
METRICS_BOX_GID = "analysis-metrics-box"
PLOT_FONT_FAMILIES = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
    "Arial Unicode MS",
    "DejaVu Sans",
]


def create_publication_figure(result: AnalysisResult, width: float = 8.0, height: float = 5.2) -> Figure:
    with matplotlib.style.context(PLOT_STYLE), matplotlib.rc_context(_publication_rc_params()):
        sns.set_theme(context=PLOT_CONTEXT, style="ticks", palette=PLOT_PALETTE)
        figure = Figure(figsize=(width, height), constrained_layout=True)
        render_result_figure(figure, result)
        return figure


def render_result_figure(figure: Figure, result: AnalysisResult) -> None:
    with matplotlib.rc_context(_publication_rc_params()):
        _ensure_constrained_layout(figure)
        figure.clear()
        if result.kind == "composite":
            _render_composite_figure(figure, result)
            return
        axis = add_result_axis(figure, result)
        render_publication_axes(axis, result)


def _publication_rc_params() -> dict[str, object]:
    return {
        "font.family": "sans-serif",
        "font.sans-serif": PLOT_FONT_FAMILIES,
        "axes.unicode_minus": False,
    }


def add_result_axis(figure: Figure, result: AnalysisResult):
    projection = _projection_for_result(result)
    if projection is None:
        return figure.add_subplot(111)
    return figure.add_subplot(111, projection=projection)


def render_publication_axes(axis, result: AnalysisResult) -> None:
    sns.set_theme(context=PLOT_CONTEXT, style="ticks", palette=PLOT_PALETTE)
    _remove_figure_level_overlays(axis.figure)
    _remove_auxiliary_axes(axis)
    _render_axis_content(axis, result)


def _render_axis_content(axis, result: AnalysisResult) -> None:
    axis.clear()
    axis.set_title(result.title, pad=18 if result.kind == "polar" else 12)

    if result.kind == "message":
        axis.axis("off")
        axis.text(0.5, 0.5, result.message or "No preview available.", ha="center", va="center", wrap=True)
        return

    if result.kind == "line":
        _render_line(axis, result)
    elif result.kind == "scatter":
        _render_scatter(axis, result)
    elif result.kind == "scatter3d":
        _render_scatter3d(axis, result)
    elif result.kind == "hist":
        _render_hist(axis, result)
    elif result.kind == "heatmap":
        _render_heatmap(axis, result)
    elif result.kind == "polar":
        _render_polar(axis, result)
    elif result.kind == "phase_raster":
        _render_phase_raster(axis, result)

    if result.kind == "scatter3d":
        axis.set_xlabel(result.x_label)
        axis.set_ylabel(result.y_label)
        axis.set_zlabel(result.z_label)
    elif result.kind != "polar":
        axis.set_xlabel(result.x_label)
        axis.set_ylabel(result.y_label)
    _apply_axis_ranges(axis, result)
    _render_reference_hlines(axis, result)
    _annotate_meta(axis, result)
    _apply_axis_spacing(axis, result)
    if result.kind not in {"polar", "scatter3d"}:
        sns.despine(ax=axis)


def _render_line(axis, result: AnalysisResult) -> None:
    if result.export_table.empty and result.series:
        frame = pd.concat(
            [
                pd.DataFrame(
                    {
                        "x": series.x,
                        "y": series.y,
                        "series": series.label,
                    }
                )
                for series in result.series
            ],
            ignore_index=True,
        )
    else:
        frame = _line_frame_from_result(result)

    if frame.empty:
        axis.text(0.5, 0.5, "No line data available.", ha="center", va="center")
        return

    has_confidence_band = {"ci_low", "ci_high"}.issubset(frame.columns) and frame["ci_low"].notna().any()
    hue = "series" if "series" in frame.columns and frame["series"].nunique() > 1 else None
    show_legend = bool(result.meta.get("show_legend", True))
    line_width = float(result.meta.get("line_width", 2.2))
    individual_alpha = float(result.meta.get("individual_alpha", 0.0))

    # Special handling for waveform display with multiple sampled waveforms
    if individual_alpha > 0 and result.series and len(result.series) > 1:
        # First series is mean, rest are individual waveforms
        mean_series = result.series[0]
        individual_series = result.series[1:]

        # Plot confidence band using ci_low/ci_high if available
        if has_confidence_band:
            valid_band = frame["ci_low"].notna() & frame["ci_high"].notna()
            if valid_band.any():
                mean_frame = frame[frame["series"] == "Mean"].sort_values("x")
                if not mean_frame.empty:
                    axis.fill_between(
                        mean_frame["x"].to_numpy(dtype=float),
                        mean_frame["ci_low"].to_numpy(dtype=float),
                        mean_frame["ci_high"].to_numpy(dtype=float),
                        color="#2F6B99",
                        alpha=0.18,
                        linewidth=0.0,
                    )

        # Plot individual waveforms with low alpha and thinner lines
        individual_line_width = line_width * 0.6
        for series in individual_series:
            axis.plot(
                series.x,
                series.y,
                color="gray",
                linewidth=individual_line_width,
                alpha=individual_alpha,
                label=None,
            )

        # Plot mean waveform last with full opacity
        axis.plot(
            mean_series.x,
            mean_series.y,
            color="#2F6B99",
            linewidth=line_width,
            label="Mean" if show_legend else None,
        )

        if show_legend:
            _place_legend_outside(axis)
        elif axis.get_legend() is not None:
            axis.get_legend().remove()
        return

    if not has_confidence_band:
        sns.lineplot(data=frame, x="x", y="y", hue=hue, linewidth=line_width, ax=axis)
        if hue is not None and show_legend:
            _place_legend_outside(axis)
        elif axis.get_legend() is not None:
            axis.get_legend().remove()
        return

    grouped_frames = (
        [(str(frame["series"].iloc[0]), frame)]
        if hue is None
        else [(str(label), subset.copy()) for label, subset in frame.groupby("series", sort=False)]
    )
    palette = sns.color_palette(PLOT_PALETTE, n_colors=max(1, len(grouped_frames)))
    for color, (label, subset) in zip(palette, grouped_frames, strict=False):
        ordered = subset.sort_values("x")
        axis.plot(
            ordered["x"].to_numpy(dtype=float),
            ordered["y"].to_numpy(dtype=float),
            color=color,
            linewidth=line_width,
            label=label if hue is not None else None,
        )
        valid_band = ordered["ci_low"].notna() & ordered["ci_high"].notna()
        if valid_band.any():
            axis.fill_between(
                ordered.loc[valid_band, "x"].to_numpy(dtype=float),
                ordered.loc[valid_band, "ci_low"].to_numpy(dtype=float),
                ordered.loc[valid_band, "ci_high"].to_numpy(dtype=float),
                color=color,
                alpha=float(result.meta.get("band_alpha", 0.18)),
                linewidth=0.0,
            )
    if hue is not None and show_legend:
        _place_legend_outside(axis)
    elif axis.get_legend() is not None:
        axis.get_legend().remove()


def _render_scatter(axis, result: AnalysisResult) -> None:
    frame = _scatter_frame_from_result(result)
    if frame.empty:
        axis.text(0.5, 0.5, "No data available.", ha="center", va="center")
        return
    hue = "series" if "series" in frame.columns and frame["series"].nunique() > 1 else None
    sns.scatterplot(
        data=frame,
        x="x",
        y="y",
        hue=hue,
        s=float(result.meta.get("marker_size", 55.0)),
        edgecolor="white",
        linewidth=0.6,
        ax=axis,
    )
    if hue is not None and bool(result.meta.get("show_legend", True)):
        _place_legend_outside(axis)
    elif axis.get_legend() is not None:
        axis.get_legend().remove()


def _render_scatter3d(axis, result: AnalysisResult) -> None:
    frame = _scatter3d_frame_from_result(result)
    if frame.empty:
        axis.text2D(0.5, 0.5, "No data available.", transform=axis.transAxes, ha="center", va="center")
        return

    marker_size = float(result.meta.get("marker_size", 55.0))
    show_legend = bool(result.meta.get("show_legend", True))
    axis.view_init(
        elev=float(result.meta.get("view_elev", 18.0)),
        azim=float(result.meta.get("view_azim", -52.0)),
    )

    for cell_type, subset in frame.groupby("series", sort=False):
        color = subset["color_hex"].iloc[0] if "color_hex" in subset.columns else "#2F6B99"
        axis.scatter(
            subset["x"],
            subset["y"],
            subset["z"],
            s=marker_size,
            c=[color],
            label=cell_type,
            edgecolors="white",
            linewidths=0.6,
            alpha=0.9,
            depthshade=True,
        )

    for centroid in result.meta.get("cluster_centroids", []):
        axis.scatter(
            [float(centroid["x"])],
            [float(centroid["y"])],
            [float(centroid["z"])],
            s=max(marker_size * 2.1, 70.0),
            c=[str(centroid.get("color_hex", "#111111"))],
            marker="X",
            edgecolors="black",
            linewidths=0.9,
            alpha=0.98,
        )

    if show_legend:
        _place_legend_outside(axis, max_columns=2)
    elif axis.get_legend() is not None:
        axis.get_legend().remove()
    axis.grid(True, alpha=0.28)


def _render_hist(axis, result: AnalysisResult) -> None:
    frame = _hist_frame_from_result(result)
    if frame.empty:
        axis.text(0.5, 0.5, "No histogram data available.", ha="center", va="center")
        return
    sns.histplot(
        data=frame,
        x="bin_left",
        weights="count",
        bins=len(frame),
        element="step",
        fill=True,
        linewidth=float(result.meta.get("line_width", 2.2)),
        ax=axis,
    )


def _render_polar(axis, result: AnalysisResult) -> None:
    line_frame = _polar_line_frame_from_result(result)
    if not line_frame.empty:
        _render_polar_line_fill(axis, result, line_frame)
        return

    if {"phase_center_rad", "mean_amplitude"}.issubset(result.export_table.columns):
        theta = result.export_table["phase_center_rad"].to_numpy(dtype=float)
        radii = result.export_table["mean_amplitude"].to_numpy(dtype=float)
        widths = (
            result.export_table["phase_right_rad"].to_numpy(dtype=float)
            - result.export_table["phase_left_rad"].to_numpy(dtype=float)
        )
    elif {"phase_center_rad", "count"}.issubset(result.export_table.columns):
        theta = result.export_table["phase_center_rad"].to_numpy(dtype=float)
        radii = result.export_table["count"].to_numpy(dtype=float)
        widths = (
            result.export_table["phase_right_rad"].to_numpy(dtype=float)
            - result.export_table["phase_left_rad"].to_numpy(dtype=float)
        )
    elif result.series:
        theta = np.asarray(result.series[0].x, dtype=float)
        radii = np.asarray(result.series[0].y, dtype=float)
        if theta.size > 1:
            widths = np.full(theta.shape, (2.0 * np.pi) / theta.size, dtype=float)
        else:
            widths = np.asarray([2.0 * np.pi], dtype=float)
    else:
        axis.text(0.5, 0.5, "No polar data available.", ha="center", va="center")
        return

    colors = plt_normalized_colors(radii)
    axis.bar(
        theta,
        radii,
        width=widths,
        bottom=0.0,
        align="center",
        color=colors,
        edgecolor="white",
        linewidth=float(result.meta.get("line_width", 0.8)),
    )
    tick_step_deg = int(result.meta.get("polar_tick_step_deg", 45))
    tick_values_deg = np.arange(0, 360, tick_step_deg, dtype=int)
    _apply_polar_axis_style(axis, result, tick_values_deg)


def _polar_line_frame_from_result(result: AnalysisResult) -> pd.DataFrame:
    if {"theta_rad", "radius"}.issubset(result.export_table.columns):
        frame = result.export_table.copy()
        if "series" not in frame.columns:
            frame["series"] = "Series 1"
        return frame
    if result.series:
        frames: list[pd.DataFrame] = []
        for series in result.series:
            frames.append(
                pd.DataFrame(
                    {
                        "theta_rad": np.asarray(series.x, dtype=float),
                        "radius": np.asarray(series.y, dtype=float),
                        "series": str(series.label),
                    }
                )
            )
        if frames:
            return pd.concat(frames, ignore_index=True)
    return pd.DataFrame(columns=["theta_rad", "radius", "series"])


def _render_polar_line_fill(axis, result: AnalysisResult, frame: pd.DataFrame) -> None:
    grouped_frames = [(str(label), subset.copy()) for label, subset in frame.groupby("series", sort=False)]
    if not grouped_frames:
        axis.text(0.5, 0.5, "No polar data available.", ha="center", va="center")
        return

    palette = sns.color_palette(PLOT_PALETTE, n_colors=max(1, len(grouped_frames)))
    line_width = float(result.meta.get("line_width", 2.2))
    fill_alpha = float(result.meta.get("polar_fill_alpha", 0.12))
    band_alpha = float(result.meta.get("band_alpha", 0.10))

    for color, (label, subset) in zip(palette, grouped_frames, strict=False):
        ordered = subset.sort_values("theta_rad").reset_index(drop=True)
        theta = ordered["theta_rad"].to_numpy(dtype=float)
        radius = ordered["radius"].to_numpy(dtype=float)
        if theta.size == 0:
            continue

        closed_theta = np.concatenate([theta, theta[:1] + 2.0 * np.pi])
        closed_radius = np.concatenate([radius, radius[:1]])
        axis.plot(closed_theta, closed_radius, color=color, linewidth=line_width, label=label)
        axis.fill(closed_theta, closed_radius, color=color, alpha=fill_alpha, linewidth=0.0)

        if {"ci_low", "ci_high"}.issubset(ordered.columns):
            valid_band = ordered["ci_low"].notna() & ordered["ci_high"].notna()
            if valid_band.any():
                band_theta = ordered.loc[valid_band, "theta_rad"].to_numpy(dtype=float)
                band_low = ordered.loc[valid_band, "ci_low"].to_numpy(dtype=float)
                band_high = ordered.loc[valid_band, "ci_high"].to_numpy(dtype=float)
                if band_theta.size > 0:
                    band_theta_closed = np.concatenate([band_theta, band_theta[:1] + 2.0 * np.pi])
                    band_low_closed = np.concatenate([band_low, band_low[:1]])
                    band_high_closed = np.concatenate([band_high, band_high[:1]])
                    axis.fill_between(
                        band_theta_closed,
                        band_low_closed,
                        band_high_closed,
                        color=color,
                        alpha=band_alpha,
                        linewidth=0.0,
                    )

    if bool(result.meta.get("show_legend", True)):
        _place_legend_outside(axis, max_columns=max(1, len(grouped_frames)))
    elif axis.get_legend() is not None:
        axis.get_legend().remove()

    tick_step_deg = int(result.meta.get("polar_tick_step_deg", 45))
    tick_values_deg = np.arange(0, 360, tick_step_deg, dtype=int)
    _apply_polar_axis_style(axis, result, tick_values_deg)


def _polar_tick_labels(tick_values_deg: np.ndarray, label_mode: str) -> list[str]:
    if label_mode == "pi":
        mapping = {
            0: "0",
            90: "π/2",
            180: "π",
            270: "3/2π",
            360: "2π",
        }
        return [mapping.get(int(value), f"{int(value)}°") for value in tick_values_deg]
    return [f"{int(value)} deg" for value in tick_values_deg]


def _render_composite_figure(figure: Figure, result: AnalysisResult) -> None:
    sns.set_theme(context=PLOT_CONTEXT, style="ticks", palette=PLOT_PALETTE)
    if not result.panels:
        axis = figure.add_subplot(111)
        _render_axis_content(
            axis,
            AnalysisResult(
                node_id=result.node_id,
                title=result.title,
                kind="message",
                message="No composite panels available.",
            ),
        )
        return

    figure.suptitle(result.title, y=0.99)
    rows, cols = _composite_grid(result)
    axes = [
        figure.add_subplot(rows, cols, index + 1, projection=_projection_for_result(panel))
        for index, panel in enumerate(result.panels)
    ]
    for axis, panel in zip(axes, result.panels, strict=False):
        _render_axis_content(axis, panel)


def _render_phase_raster(axis, result: AnalysisResult) -> None:
    frame = result.export_table.copy()
    if frame.empty:
        axis.text(0.5, 0.5, "No phase raster data available.", ha="center", va="center")
        return

    units = frame[["unit_order", "unit_label"]].drop_duplicates().sort_values("unit_order")
    palette = sns.color_palette("husl", n_colors=max(1, len(units)))
    color_by_order = {int(row.unit_order): palette[index] for index, row in enumerate(units.itertuples())}
    marker_halfwidth_deg = float(result.meta.get("marker_halfwidth_deg", 8.0))
    line_width = float(result.meta.get("line_width", 2.2))
    cycle_line_alpha = float(result.meta.get("cycle_line_alpha", 0.7))
    show_wave_overlay = bool(result.meta.get("show_wave_overlay", True))
    wave_overlay_alpha = float(result.meta.get("wave_overlay_alpha", 0.85))

    for unit_order in units["unit_order"]:
        subset = frame[frame["unit_order"] == unit_order]
        axis.hlines(
            np.full(len(subset), float(unit_order), dtype=float),
            subset["x_deg"] - marker_halfwidth_deg,
            subset["x_deg"] + marker_halfwidth_deg,
            colors=[color_by_order[int(unit_order)]],
            linewidth=line_width,
            alpha=0.95,
        )

    displayed_cycles = int(result.meta.get("displayed_cycles", int(frame["cycle_index"].max()) + 1))
    for boundary_deg in np.arange(0.0, displayed_cycles * 360.0 + 0.5, 360.0):
        axis.axvline(boundary_deg, color="#2F6B99", linewidth=1.0, alpha=cycle_line_alpha)

    max_x_deg = float(frame["x_deg"].max())
    wave_center = float(units["unit_order"].max()) + 0.9
    if show_wave_overlay:
        wave_x_deg = np.linspace(0.0, max_x_deg, num=max(400, displayed_cycles * 80))
        axis.plot(
            wave_x_deg,
            wave_center + 0.35 * np.sin(np.deg2rad(wave_x_deg)),
            color="#8FB3C9",
            linewidth=max(1.0, line_width * 0.82),
            alpha=wave_overlay_alpha,
        )
        if displayed_cycles >= 1:
            axis.text(180.0, wave_center + 0.55, "180 deg", ha="center", va="bottom", fontsize=9)
            axis.text(360.0, wave_center + 0.72, "360 deg", ha="center", va="bottom", fontsize=9)

    axis.set_xlim(-12.0, max_x_deg + 12.0)
    axis.set_ylim(-0.7, wave_center + 0.95)
    axis.set_yticks(units["unit_order"].to_numpy(dtype=float))
    axis.set_yticklabels(units["unit_label"].tolist())


def _render_heatmap(axis, result: AnalysisResult) -> None:
    if result.export_table.empty:
        matrix = np.asarray(result.image) if result.image is not None else np.empty((0, 0))
        frame = pd.DataFrame(matrix)
    else:
        frame = result.export_table.copy()
    if frame.empty:
        axis.text(0.5, 0.5, "No matrix data available.", ha="center", va="center")
        return

    if _has_numeric_heatmap_axes(result, frame.shape):
        _render_numeric_heatmap(axis, frame.to_numpy(dtype=float), result)
        return

    if result.meta.get("x_tick_labels") and result.meta.get("y_tick_labels"):
        frame.columns = list(result.meta["x_tick_labels"])
        frame.index = list(result.meta["y_tick_labels"])
        xticklabels = True
        yticklabels = True
    else:
        xticklabels = _sparse_tick_labels(result.image_x, frame.shape[1])
        yticklabels = _sparse_tick_labels(result.image_y, frame.shape[0])
    cmap = str(result.meta.get("colormap", "mako"))
    sns.heatmap(
        frame,
        cmap=cmap,
        ax=axis,
        cbar=bool(result.meta.get("show_colorbar", True)),
        vmin=result.meta.get("vmin"),
        vmax=result.meta.get("vmax"),
        xticklabels=xticklabels,
        yticklabels=yticklabels,
        cbar_kws={"label": result.color_label or "", "pad": 0.04},
    )
    axis.tick_params(axis="x", rotation=45)
    axis.tick_params(axis="y", rotation=0)


def _render_numeric_heatmap(axis, matrix: np.ndarray, result: AnalysisResult) -> None:
    x_values = np.asarray(result.image_x, dtype=float)
    y_values = np.asarray(result.image_y, dtype=float)
    image = axis.imshow(
        matrix,
        origin="lower",
        aspect="auto",
        cmap=str(result.meta.get("colormap", "mako")),
        vmin=result.meta.get("vmin"),
        vmax=result.meta.get("vmax"),
        extent=_heatmap_extent(x_values, y_values),
    )
    if bool(result.meta.get("show_colorbar", True)):
        axis.figure.colorbar(image, ax=axis, label=result.color_label or "", pad=0.04)


def _has_numeric_heatmap_axes(result: AnalysisResult, shape: tuple[int, int]) -> bool:
    if result.meta.get("x_tick_labels") or result.meta.get("y_tick_labels"):
        return False
    if result.image_x is None or result.image_y is None:
        return False
    return len(result.image_x) == shape[1] and len(result.image_y) == shape[0]


def _heatmap_extent(x_values: np.ndarray, y_values: np.ndarray) -> tuple[float, float, float, float]:
    return (
        *_axis_extent(x_values),
        *_axis_extent(y_values),
    )


def _axis_extent(values: np.ndarray) -> tuple[float, float]:
    if values.size == 1:
        center = float(values[0])
        return center - 0.5, center + 0.5
    deltas = np.diff(values.astype(float))
    left_step = deltas[0]
    right_step = deltas[-1]
    return float(values[0] - left_step / 2.0), float(values[-1] + right_step / 2.0)


def _line_frame_from_result(result: AnalysisResult) -> pd.DataFrame:
    if {"x", "y"}.issubset(result.export_table.columns):
        frame = pd.DataFrame(
            {
                "x": result.export_table["x"],
                "y": result.export_table["y"],
                "series": result.export_table.get("series", pd.Series(["Signal"] * len(result.export_table))),
            }
        )
        if "ci_low" in result.export_table.columns:
            frame["ci_low"] = result.export_table["ci_low"]
        if "ci_high" in result.export_table.columns:
            frame["ci_high"] = result.export_table["ci_high"]
        return frame
    if {"frequency_hz", "power_db"}.issubset(result.export_table.columns):
        return pd.DataFrame(
            {"x": result.export_table["frequency_hz"], "y": result.export_table["power_db"], "series": "Signal"}
        )
    if {"frequency_hz", "power"}.issubset(result.export_table.columns):
        return pd.DataFrame({"x": result.export_table["frequency_hz"], "y": result.export_table["power"], "series": "Signal"})
    if {"frequency_hz", "coherence"}.issubset(result.export_table.columns):
        return pd.DataFrame(
            {"x": result.export_table["frequency_hz"], "y": result.export_table["coherence"], "series": "Signal"}
        )
    if {"frequency_hz", "negative_log10_pvalue"}.issubset(result.export_table.columns):
        return pd.DataFrame(
            {
                "x": result.export_table["frequency_hz"],
                "y": result.export_table["negative_log10_pvalue"],
                "series": "Signal",
            }
        )
    if {"time_s", "rate_hz"}.issubset(result.export_table.columns):
        return pd.DataFrame({"x": result.export_table["time_s"], "y": result.export_table["rate_hz"], "series": "Signal"})
    if {"time_s", "power"}.issubset(result.export_table.columns):
        return pd.DataFrame({"x": result.export_table["time_s"], "y": result.export_table["power"], "series": "Signal"})
    if {"time_s", "amplitude"}.issubset(result.export_table.columns):
        return pd.DataFrame({"x": result.export_table["time_s"], "y": result.export_table["amplitude"], "series": "Signal"})
    if {"time_ms", "amplitude"}.issubset(result.export_table.columns):
        return pd.DataFrame({"x": result.export_table["time_ms"], "y": result.export_table["amplitude"], "series": "Signal"})
    if {"lag_ms", "amplitude"}.issubset(result.export_table.columns):
        return pd.DataFrame({"x": result.export_table["lag_ms"], "y": result.export_table["amplitude"], "series": "Signal"})
    return pd.DataFrame(columns=["x", "y", "series"])


def _scatter_frame_from_result(result: AnalysisResult) -> pd.DataFrame:
    if {"width_ms", "firing_rate_hz"}.issubset(result.export_table.columns):
        frame = pd.DataFrame(
            {
                "x": result.export_table["width_ms"],
                "y": result.export_table["firing_rate_hz"],
                "series": result.export_table.get("region", pd.Series(["Units"] * len(result.export_table))),
            }
        )
        return frame
    if result.series:
        series = result.series[0]
        return pd.DataFrame({"x": series.x, "y": series.y, "series": series.label})
    return pd.DataFrame(columns=["x", "y", "series"])


def _scatter3d_frame_from_result(result: AnalysisResult) -> pd.DataFrame:
    if {"x_value", "y_value", "z_value"}.issubset(result.export_table.columns):
        return pd.DataFrame(
            {
                "x": result.export_table["x_value"],
                "y": result.export_table["y_value"],
                "z": result.export_table["z_value"],
                "series": result.export_table.get("putative_cell_type", pd.Series(["Units"] * len(result.export_table))),
                "color_hex": result.export_table.get("color_hex", pd.Series(["#2F6B99"] * len(result.export_table))),
            }
        )
    return pd.DataFrame(columns=["x", "y", "z", "series", "color_hex"])


def _hist_frame_from_result(result: AnalysisResult) -> pd.DataFrame:
    if {"bin_left_s", "count"}.issubset(result.export_table.columns):
        return pd.DataFrame({"bin_left": result.export_table["bin_left_s"], "count": result.export_table["count"]})
    if {"lag_s", "count"}.issubset(result.export_table.columns):
        return pd.DataFrame({"bin_left": result.export_table["lag_s"], "count": result.export_table["count"]})
    if {"bin_left_rad", "count"}.issubset(result.export_table.columns):
        return pd.DataFrame({"bin_left": result.export_table["bin_left_rad"], "count": result.export_table["count"]})
    if result.series:
        series = result.series[0]
        return pd.DataFrame({"bin_left": series.x, "count": series.y})
    return pd.DataFrame(columns=["bin_left", "count"])


def _annotate_meta(axis, result: AnalysisResult) -> None:
    if result.meta.get("show_metrics_box") is False:
        return
    keys = [
        key
        for key in ("width_ms", "snr", "plv", "mean_phase_rad", "peak_phase_hz", "peak_amp_hz", "peak_mi")
        if key in result.meta
    ]
    if not keys:
        return
    lines = []
    for key in keys:
        value = result.meta[key]
        if isinstance(value, float):
            lines.append(f"{key}: {value:.3f}")
        else:
            lines.append(f"{key}: {value}")
    annotation = "\n".join(lines)
    if result.kind == "polar" or len(_content_axes(axis.figure)) <= 1:
        artist = axis.set_title(annotation, loc="right", fontsize=9, pad=10)
        artist.set_multialignment("left")
        artist.set_bbox({"boxstyle": "round", "facecolor": "white", "alpha": 0.92, "edgecolor": "0.7"})
    else:
        artist = axis.text(
            0.98,
            0.98,
            annotation,
            transform=axis.transAxes,
            ha="right",
            va="top",
            fontsize=8.5,
            clip_on=False,
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.9, "edgecolor": "0.7"},
        )
    artist.set_gid(METRICS_BOX_GID)
    artist.set_in_layout(True)


def _render_reference_hlines(axis, result: AnalysisResult) -> None:
    for line in result.meta.get("reference_hlines", []):
        axis.axhline(
            float(line["y"]),
            color=str(line.get("color", "#C44E52")),
            linestyle=str(line.get("linestyle", "--")),
            linewidth=float(line.get("linewidth", 1.2)),
            alpha=float(line.get("alpha", 0.85)),
        )


def _remove_auxiliary_axes(axis) -> None:
    figure = axis.figure
    for extra_axis in list(figure.axes):
        if extra_axis is not axis:
            extra_axis.remove()


def _remove_figure_level_overlays(figure: Figure) -> None:
    for text in list(figure.texts):
        if text.get_gid() == METRICS_BOX_GID:
            text.remove()


def _ensure_constrained_layout(figure: Figure) -> None:
    if hasattr(figure, "set_layout_engine"):
        try:
            figure.set_layout_engine("constrained")
            return
        except Exception:
            pass
    try:
        figure.set_constrained_layout(True)
    except Exception:
        pass


def _content_axes(figure: Figure) -> list:
    return [axis for axis in figure.axes if axis.get_label() != "<colorbar>"]


def _apply_axis_spacing(axis, result: AnalysisResult) -> None:
    if result.kind == "polar":
        axis.tick_params(axis="x", pad=10)
        axis.tick_params(axis="y", pad=8)
    elif result.kind != "scatter3d":
        axis.tick_params(axis="x", pad=4)
        axis.tick_params(axis="y", pad=4)


def _apply_polar_axis_style(axis, result: AnalysisResult, tick_values_deg: np.ndarray) -> None:
    axis.set_theta_zero_location(str(result.meta.get("polar_zero_location", "N")))
    direction = str(result.meta.get("polar_direction", "clockwise"))
    axis.set_theta_direction(-1 if direction == "clockwise" else 1)
    axis.set_rlabel_position(float(result.meta.get("polar_rlabel_position_deg", 112.5)))
    axis.set_xticks(np.deg2rad(tick_values_deg))
    axis.set_xticklabels(_polar_tick_labels(tick_values_deg, str(result.meta.get("polar_tick_label_mode", "deg"))))
    show_polar_grid = bool(result.meta.get("show_polar_grid", True))
    if show_polar_grid:
        axis.grid(True, alpha=0.35)
    else:
        axis.grid(False)


def _place_legend_outside(axis, max_columns: int = 3) -> None:
    handles, labels = axis.get_legend_handles_labels()
    filtered: list[tuple[object, str]] = []
    seen_labels: set[str] = set()
    for handle, label in zip(handles, labels, strict=False):
        if not label or label.startswith("_") or label in seen_labels:
            continue
        filtered.append((handle, label))
        seen_labels.add(label)

    existing = axis.get_legend()
    if existing is not None:
        existing.remove()
    if not filtered:
        return

    legend = axis.legend(
        [handle for handle, _ in filtered],
        [label for _, label in filtered],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10 if axis.name == "polar" else -0.14),
        ncol=min(max_columns, len(filtered)),
        frameon=False,
        title=None,
        borderaxespad=0.0,
    )
    legend.set_in_layout(True)


def _projection_for_result(result: AnalysisResult) -> str | None:
    if result.kind == "polar":
        return "polar"
    if result.kind == "scatter3d":
        return "3d"
    return None


def _composite_grid(result: AnalysisResult) -> tuple[int, int]:
    layout = result.meta.get("layout", {})
    rows = int(layout.get("rows", 1))
    cols = int(layout.get("cols", len(result.panels) or 1))
    if rows <= 0:
        rows = 1
    if cols <= 0:
        cols = max(1, len(result.panels))
    if rows * cols < len(result.panels):
        cols = int(np.ceil(len(result.panels) / rows))
    return rows, cols


def plt_normalized_colors(values: np.ndarray):
    values = np.asarray(values, dtype=float)
    if values.size == 0 or np.allclose(values.max(), values.min()):
        return ["#2F6B99"] * len(values)
    normalized = (values - values.min()) / (values.max() - values.min())
    return matplotlib.colormaps["mako"](normalized)


def _apply_axis_ranges(axis, result: AnalysisResult) -> None:
    if result.meta.get("x_range") and result.kind != "polar":
        axis.set_xlim(*result.meta["x_range"])
    if result.meta.get("y_range"):
        axis.set_ylim(*result.meta["y_range"])


def _sparse_tick_labels(values: Iterable[float] | None, count: int) -> list[str] | bool:
    if values is None:
        return False
    values = list(values)
    if len(values) != count or count <= 0:
        return False
    keep = max(1, count // 6)
    labels = []
    for index, value in enumerate(values):
        if index % keep == 0 or index == count - 1:
            labels.append(f"{value:.2f}")
        else:
            labels.append("")
    return labels
