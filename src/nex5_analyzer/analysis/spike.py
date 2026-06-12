from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import signal
from scipy.cluster.vq import kmeans2
from elephant.waveform_features import waveform_snr
from scipy.ndimage import gaussian_filter1d

from ..models import AnalysisNode, AnalysisResult, PlotSeries
from .common import base_spectrogram_kwargs, correlogram_result, waveform_width_ms
from .runtime import AnalysisRuntime


SUMMARY_FEATURE_LABELS = {
    "half_width_ms": "Half Width (ms)",
    "firing_rate_hz": "Firing Rate (Hz)",
    "trough_to_peak_ms": "Trough-to-Peak Width (ms)",
    "snr": "SNR",
    "peak_to_trough_ratio": "Peak/Trough Ratio",
    "peak_amplitude": "Peak Amplitude",
    "trough_amplitude": "Trough Amplitude",
    "spike_count": "Spike Count",
}
WAVEFORM_CLUSTER_FEATURE_KEYS = (
    "half_width_ms",
    "trough_to_peak_ms",
    "firing_rate_hz",
    "snr",
    "peak_to_trough_ratio",
)
CELL_TYPE_COLOR_MAP = {
    "Putative excitatory": "#1f77b4",
    "Putative inhibitory": "#d62728",
    "Unclassified": "#7f7f7f",
}


def _spectrogram_kwargs(sample_rate_hz: float, params: dict, *, nperseg: int, noverlap: int) -> dict[str, object]:
    return base_spectrogram_kwargs(sample_rate_hz, nperseg, noverlap, params)


def _welch_kwargs(sample_rate_hz: float, params: dict, *, nperseg: int, noverlap: int) -> dict[str, object]:
    kwargs = _spectrogram_kwargs(sample_rate_hz, params, nperseg=nperseg, noverlap=noverlap)
    if "welch_average" in params:
        kwargs["average"] = str(params["welch_average"])
    return kwargs


def _rate_trace(
    spike_times_s: np.ndarray,
    duration_s: float,
    *,
    bin_size_ms: float,
    smoothing_sigma_ms: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    bin_size_s = float(bin_size_ms) / 1000.0
    edges = np.arange(0.0, duration_s + bin_size_s, bin_size_s)
    counts, _ = np.histogram(spike_times_s, bins=edges)
    rates = counts / bin_size_s
    if float(smoothing_sigma_ms) > 0.0:
        sigma_bins = float(smoothing_sigma_ms) / float(bin_size_ms)
        rates = gaussian_filter1d(rates.astype(float), sigma=sigma_bins)
    centers = edges[:-1] + bin_size_s / 2.0
    return centers, rates.astype(float), bin_size_s


def _build_rate_trace_state(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> dict[str, object]:
    spike = runtime.load_spike(node.source_refs["spike"])
    duration_s = float(runtime.session.metadata["duration_s"])
    centers, rates, bin_size_s = _rate_trace(
        spike.timestamps_s,
        duration_s,
        bin_size_ms=float(params["bin_size_ms"]),
        smoothing_sigma_ms=float(params["smoothing_sigma_ms"]),
    )
    return {
        "centers": centers,
        "rates": rates,
        "bin_size_s": float(bin_size_s),
        "duration_s": duration_s,
        "source_id": node.source_refs["spike"],
    }


def _shared_rate_trace_state(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> dict[str, object]:
    cache_key = (
        "spike",
        "rate_trace_state",
        node.source_refs["spike"],
        float(params["bin_size_ms"]),
        float(params["smoothing_sigma_ms"]),
    )
    return runtime.cache_get_or_create(cache_key, lambda: _build_rate_trace_state(runtime, node, params))


def _summary_feature_label(feature_key: str) -> str:
    return SUMMARY_FEATURE_LABELS.get(feature_key, feature_key)


def _safe_waveform_snr(waveforms: np.ndarray | None) -> float:
    if waveforms is None or waveforms.size == 0:
        return float("nan")
    value = float(waveform_snr(waveforms))
    return value if np.isfinite(value) else float("nan")


def _half_width_ms(mean_waveform: np.ndarray, waveform_sample_rate_hz: float | None) -> float:
    if waveform_sample_rate_hz in (None, 0) or mean_waveform.size == 0:
        return float("nan")
    trough_index = int(np.argmin(mean_waveform))
    if not np.isfinite(mean_waveform[trough_index]):
        return float("nan")
    widths, _, _, _ = signal.peak_widths(-np.asarray(mean_waveform, dtype=float), [trough_index], rel_height=0.5)
    if widths.size == 0:
        return float("nan")
    return float(widths[0]) / float(waveform_sample_rate_hz) * 1000.0


def _peak_to_trough_ratio(mean_waveform: np.ndarray) -> float:
    peak = float(np.max(mean_waveform))
    trough = abs(float(np.min(mean_waveform)))
    if trough <= 0.0:
        return float("nan")
    return peak / trough


def _unit_waveform_summary_row(runtime: AnalysisRuntime, unit, session_duration_s: float) -> dict[str, object] | None:
    data = runtime.load_spike(unit.variable_name)
    if data.waveforms is None or data.waveforms.size == 0:
        return None

    mean_waveform = np.asarray(data.waveforms, dtype=float).mean(axis=0)
    waveform_rate_hz = float(data.waveform_sample_rate_hz or unit.waveform_sample_rate_hz or 0.0) or None
    trough_to_peak_ms = waveform_width_ms(mean_waveform, waveform_rate_hz)
    half_width_ms = _half_width_ms(mean_waveform, waveform_rate_hz)
    spike_count = int(len(data.timestamps_s))

    return {
        "unit": unit.display_name,
        "channel_id": unit.channel_id,
        "subject": unit.subject or "",
        "region": unit.region or "",
        "region_label": unit.region_label,
        "spike_count": spike_count,
        "firing_rate_hz": float(spike_count / session_duration_s) if session_duration_s > 0 else float("nan"),
        "snr": _safe_waveform_snr(data.waveforms),
        "half_width_ms": half_width_ms,
        "trough_to_peak_ms": trough_to_peak_ms,
        "width_ms": trough_to_peak_ms,
        "peak_amplitude": float(np.max(mean_waveform)),
        "trough_amplitude": float(np.min(mean_waveform)),
        "peak_to_trough_ratio": _peak_to_trough_ratio(mean_waveform),
    }


def _build_waveform_summary_frame(runtime: AnalysisRuntime, params: dict) -> pd.DataFrame:
    session = runtime.session
    rows = []
    for unit in session.spike_units[: int(params["summary_max_units"])]:
        row = _unit_waveform_summary_row(runtime, unit, float(session.metadata["duration_s"]))
        if row is not None:
            rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return _assign_putative_cell_types(frame, cluster_seed=int(params.get("cluster_seed", 7)))


def _assign_putative_cell_types(frame: pd.DataFrame, *, cluster_seed: int) -> pd.DataFrame:
    classified = frame.copy()
    classified["cluster_id"] = -1
    classified["putative_cell_type"] = "Unclassified"
    classified["color_hex"] = CELL_TYPE_COLOR_MAP["Unclassified"]

    feature_frame = classified.loc[:, WAVEFORM_CLUSTER_FEATURE_KEYS].apply(pd.to_numeric, errors="coerce")
    valid_mask = np.isfinite(feature_frame.to_numpy(dtype=float)).all(axis=1)
    if int(valid_mask.sum()) < 2:
        return classified

    valid_index = feature_frame.index[valid_mask]
    values = feature_frame.loc[valid_index].to_numpy(dtype=float)
    std = values.std(axis=0)
    varying_columns = std > 1e-9
    if not np.any(varying_columns):
        return classified

    scaled = (values[:, varying_columns] - values[:, varying_columns].mean(axis=0)) / std[varying_columns]
    if np.unique(np.round(scaled, decimals=8), axis=0).shape[0] < 2:
        return classified

    _, labels = kmeans2(
        scaled,
        2,
        minit="++",
        missing="raise",
        rng=np.random.default_rng(cluster_seed),
    )
    labels = np.asarray(labels, dtype=int)
    classified.loc[valid_index, "cluster_id"] = labels

    cluster_summary = (
        classified.loc[valid_index, ["cluster_id", "half_width_ms", "trough_to_peak_ms", "firing_rate_hz"]]
        .groupby("cluster_id")
        .mean()
        .sort_values(
            by=["half_width_ms", "trough_to_peak_ms", "firing_rate_hz"],
            ascending=[True, True, False],
        )
    )
    inhibitory_cluster = int(cluster_summary.index[0])
    excitatory_cluster = next(
        (int(cluster_id) for cluster_id in cluster_summary.index if int(cluster_id) != inhibitory_cluster),
        inhibitory_cluster,
    )

    classified.loc[classified["cluster_id"] == inhibitory_cluster, "putative_cell_type"] = "Putative inhibitory"
    classified.loc[classified["cluster_id"] == excitatory_cluster, "putative_cell_type"] = "Putative excitatory"
    classified["color_hex"] = classified["putative_cell_type"].map(CELL_TYPE_COLOR_MAP).fillna(
        CELL_TYPE_COLOR_MAP["Unclassified"]
    )
    return classified


def compute_waveform_characterization(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    session = runtime.session
    if "spike" not in node.source_refs:
        frame = _build_waveform_summary_frame(runtime, params)
        if frame.empty:
            return AnalysisResult(
                node_id=node.node_id,
                title="Unit Classification Summary",
                kind="message",
                message="No waveform data available for spike unit classification.",
            )

        x_feature = str(params["summary_x_feature"])
        y_feature = str(params["summary_y_feature"])
        z_feature = str(params["summary_z_feature"])
        export_frame = frame.copy()
        export_frame["x_value"] = export_frame[x_feature]
        export_frame["y_value"] = export_frame[y_feature]
        export_frame["z_value"] = export_frame[z_feature]

        centroids = []
        centroid_frame = export_frame[export_frame["cluster_id"] >= 0]
        for cluster_id, subset in centroid_frame.groupby("cluster_id", sort=True):
            cell_type = str(subset["putative_cell_type"].iloc[0])
            centroids.append(
                {
                    "cluster_id": int(cluster_id),
                    "putative_cell_type": cell_type,
                    "x": float(subset["x_value"].mean()),
                    "y": float(subset["y_value"].mean()),
                    "z": float(subset["z_value"].mean()),
                    "color_hex": CELL_TYPE_COLOR_MAP.get(cell_type, CELL_TYPE_COLOR_MAP["Unclassified"]),
                }
            )

        return AnalysisResult(
            node_id=node.node_id,
            title="Unit Classification Summary",
            kind="scatter3d",
            x_label=_summary_feature_label(x_feature),
            y_label=_summary_feature_label(y_feature),
            z_label=_summary_feature_label(z_feature),
            color_label="Putative Cell Type",
            export_table=export_frame,
            meta={
                "x_feature": x_feature,
                "y_feature": y_feature,
                "z_feature": z_feature,
                "cluster_centroids": centroids,
                "subtitle": f"{len(export_frame)} units grouped into two putative cell-type clusters",
            },
        )

    spike = runtime.load_spike(node.source_refs["spike"])
    if spike.waveforms is None or spike.waveforms.size == 0:
        return AnalysisResult(node.node_id, f"Waveform - {node.label}", "message", message="No waveform data available.")

    waveforms = np.asarray(spike.waveforms, dtype=float)
    mean_waveform = waveforms.mean(axis=0)
    std_waveform = waveforms.std(axis=0)
    waveform_rate = float(spike.waveform_sample_rate_hz or 1.0)
    time_ms = np.arange(len(mean_waveform), dtype=float) / waveform_rate * 1000.0

    # Determine max individual waveforms to display
    max_display = int(params.get("waveform_max_display", 0))
    n_waveforms = len(waveforms)
    display_count = n_waveforms if max_display <= 0 else min(max_display, n_waveforms)
    if display_count < n_waveforms:
        # Uniformly sample waveforms for display when a smaller cap is requested.
        indices = np.linspace(0, n_waveforms - 1, display_count, dtype=int)
        display_waveforms = waveforms[indices]
    else:
        display_waveforms = waveforms

    # Build series: mean waveform + displayed individual waveforms.
    series = [PlotSeries(label="Mean", x=time_ms, y=mean_waveform)]
    export_frames = [
        pd.DataFrame(
            {
                "x": time_ms,
                "y": mean_waveform,
                "series": "Mean",
                "time_ms": time_ms,
                "amplitude": mean_waveform,
                "ci_low": mean_waveform - std_waveform,
                "ci_high": mean_waveform + std_waveform,
                "source_id": node.source_refs["spike"],
                "waveform_index": -1,
            }
        )
    ]

    for i, wf in enumerate(display_waveforms):
        label = f"Spike {i + 1}"
        series.append(PlotSeries(label=label, x=time_ms, y=wf))
        export_frames.append(
            pd.DataFrame(
                {
                    "x": time_ms,
                    "y": wf,
                    "series": label,
                    "time_ms": time_ms,
                    "amplitude": wf,
                    "ci_low": np.nan,
                    "ci_high": np.nan,
                    "source_id": node.source_refs["spike"],
                    "waveform_index": i,
                }
            )
        )

    frame = pd.concat(export_frames, ignore_index=True)

    return AnalysisResult(
        node_id=node.node_id,
        title=f"Waveform - {node.label}",
        kind="line",
        x_label="Time (ms)",
        y_label="Amplitude",
        series=series,
        export_table=frame,
        meta={
            "width_ms": waveform_width_ms(mean_waveform, spike.waveform_sample_rate_hz),
            "trough_to_peak_ms": waveform_width_ms(mean_waveform, spike.waveform_sample_rate_hz),
            "half_width_ms": _half_width_ms(mean_waveform, spike.waveform_sample_rate_hz),
            "snr": _safe_waveform_snr(spike.waveforms),
            "n_waveforms": n_waveforms,
            "n_displayed": len(display_waveforms),
            "show_legend": bool(params.get("plot_show_legend", True)),
            "line_width": float(params.get("plot_line_width", 2.2)),
            "individual_alpha": float(params.get("waveform_individual_alpha", 0.15)),
        },
    )


def compute_firing_rate(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    state = _shared_rate_trace_state(runtime, node, params)
    centers = np.asarray(state["centers"], dtype=float)
    rates = np.asarray(state["rates"], dtype=float)
    frame = pd.DataFrame({"time_s": centers, "rate_hz": rates, "source_id": state["source_id"]})
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Firing Rate - {node.label}",
        kind="line",
        x_label="Time (s)",
        y_label="Rate (Hz)",
        series=[PlotSeries(label=node.label, x=centers, y=rates)],
        export_table=frame,
    )


def compute_rate_power_metrics(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    state = _shared_rate_trace_state(runtime, node, params)
    centers = np.asarray(state["centers"], dtype=float)
    rates = np.asarray(state["rates"], dtype=float)
    bin_size_s = float(state["bin_size_s"])
    if rates.size < 8:
        return AnalysisResult(
            node_id=node.node_id,
            title=f"Spike-rate Power Metrics - {node.label}",
            kind="message",
            message="Spike rate trace is too short for spectral analysis.",
        )

    rate_sampling_hz = 1.0 / bin_size_s
    nperseg = min(int(params["nperseg"]), len(rates))
    noverlap = min(int(params["noverlap"]), max(0, nperseg - 1))
    if nperseg < 8:
        return AnalysisResult(
            node_id=node.node_id,
            title=f"Spike-rate Power Metrics - {node.label}",
            kind="message",
            message="Need at least 8 rate bins for power metrics.",
        )

    spec_freq_hz, spec_times_s, spec_power = signal.spectrogram(
        rates,
        **_spectrogram_kwargs(rate_sampling_hz, params, nperseg=nperseg, noverlap=noverlap),
    )
    max_freq_hz = float(params["max_freq_hz"])
    spec_mask = spec_freq_hz <= max_freq_hz
    spec_matrix_db = 10.0 * np.log10(np.maximum(spec_power[spec_mask], 1e-12))
    spec_times_s = spec_times_s + float(centers[0])
    spectrogram_panel = AnalysisResult(
        node_id=f"{node.node_id}:spectrogram",
        title="Rate Spectrogram",
        kind="heatmap",
        x_label="Time (s)",
        y_label="Frequency (Hz)",
        color_label="Power (dB)",
        image=spec_matrix_db,
        image_x=spec_times_s,
        image_y=spec_freq_hz[spec_mask],
        export_table=pd.DataFrame(spec_matrix_db, index=np.round(spec_freq_hz[spec_mask], 6), columns=np.round(spec_times_s, 6)),
        meta={"vmin": float(params["vmin_db"]), "vmax": float(params["vmax_db"])},
    )
    spectrogram_panel.export_table.index.name = "frequency_hz"

    psd_freq_hz, psd_power = signal.welch(
        rates,
        **_welch_kwargs(rate_sampling_hz, params, nperseg=nperseg, noverlap=noverlap),
    )
    psd_mask = psd_freq_hz <= max_freq_hz
    psd_power_db = 10.0 * np.log10(np.maximum(psd_power[psd_mask], 1e-12))
    psd_frame = pd.DataFrame(
        {
            "frequency_hz": psd_freq_hz[psd_mask],
            "power": psd_power[psd_mask],
            "power_db": psd_power_db,
            "source_id": state["source_id"],
        }
    )
    psd_panel = AnalysisResult(
        node_id=f"{node.node_id}:psd",
        title="Rate PSD",
        kind="line",
        x_label="Frequency (Hz)",
        y_label="Power (dB)",
        series=[PlotSeries(label=node.label, x=psd_frame["frequency_hz"].to_numpy(), y=psd_frame["power_db"].to_numpy())],
        export_table=psd_frame,
    )

    spec_time_grid, spec_freq_grid = np.meshgrid(spec_times_s, spec_freq_hz[spec_mask])
    combined_export = pd.concat(
        [
            pd.DataFrame(
                {
                    "panel": "spectrogram",
                    "time_s": spec_time_grid.ravel(),
                    "frequency_hz": spec_freq_grid.ravel(),
                    "power_db": spec_matrix_db.ravel(),
                }
            ),
            pd.DataFrame(
                {
                    "panel": "psd",
                    "time_s": np.nan,
                    "frequency_hz": psd_frame["frequency_hz"],
                    "power_db": psd_frame["power_db"],
                }
            ),
        ],
        ignore_index=True,
    )
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Spike-rate Power Metrics - {node.label}",
        kind="composite",
        export_table=combined_export,
        panels=[spectrogram_panel, psd_panel],
    )


def compute_isi(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    spike = runtime.load_spike(node.source_refs["spike"])
    intervals = np.diff(np.sort(spike.timestamps_s))
    max_interval_s = float(params["max_interval_ms"]) / 1000.0
    bin_size_s = float(params["bin_size_ms"]) / 1000.0
    edges = np.arange(0.0, max_interval_s + bin_size_s, bin_size_s)
    counts, edges = np.histogram(intervals, bins=edges)
    frame = pd.DataFrame(
        {
            "bin_left_s": edges[:-1],
            "bin_right_s": edges[1:],
            "count": counts,
            "source_id": node.source_refs["spike"],
        }
    )
    return AnalysisResult(
        node_id=node.node_id,
        title=f"ISI - {node.label}",
        kind="hist",
        x_label="Interval (s)",
        y_label="Count",
        series=[PlotSeries(label=node.label, x=edges[:-1], y=counts)],
        export_table=frame,
    )


def compute_autocorrelation(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    spike = runtime.load_spike(node.source_refs["spike"])
    return correlogram_result(
        node_id=node.node_id,
        title=f"Autocorrelation - {node.label}",
        first=spike.timestamps_s,
        second=spike.timestamps_s,
        bin_size_s=float(params["bin_size_ms"]) / 1000.0,
        max_lag_s=float(params["max_lag_ms"]) / 1000.0,
        exclude_zero=True,
        source_id=node.source_refs["spike"],
    )


def compute_cross_correlation(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    first = runtime.load_spike(node.source_refs["spike_a"])
    second = runtime.load_spike(node.source_refs["spike_b"])
    return correlogram_result(
        node_id=node.node_id,
        title=f"Cross-correlation - {node.label}",
        first=first.timestamps_s,
        second=second.timestamps_s,
        bin_size_s=float(params["bin_size_ms"]) / 1000.0,
        max_lag_s=float(params["max_lag_ms"]) / 1000.0,
        exclude_zero=False,
        source_id=f"{node.source_refs['spike_a']}::{node.source_refs['spike_b']}",
    )
