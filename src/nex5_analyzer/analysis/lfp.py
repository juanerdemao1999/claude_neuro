from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import signal

from ..models import AnalysisNode, AnalysisResult, PlotSeries
from .common import bandpass
from .runtime import AnalysisRuntime


PSD_DEFAULT_Y_RANGE = (-70.0, 0.0)
SPECTROGRAM_DEFAULT_COLOR_RANGE = (-80.0, -20.0)


def _spectrogram_kwargs(sample_rate_hz: float, params: dict) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "fs": sample_rate_hz,
        "nperseg": int(params["nperseg"]),
        "noverlap": int(params["noverlap"]),
    }
    if "window_function" in params:
        kwargs["window"] = str(params["window_function"])
    if "detrend_mode" in params:
        kwargs["detrend"] = False if str(params["detrend_mode"]) == "none" else str(params["detrend_mode"])
    if "spectrum_scaling" in params:
        kwargs["scaling"] = str(params["spectrum_scaling"])
    return kwargs


def _welch_kwargs(sample_rate_hz: float, params: dict) -> dict[str, object]:
    kwargs = _spectrogram_kwargs(sample_rate_hz, params)
    if "welch_average" in params:
        kwargs["average"] = str(params["welch_average"])
    return kwargs


def _robust_db_range(
    values: np.ndarray,
    *,
    lower_percentile: float = 1.0,
    upper_percentile: float = 99.0,
    min_span_db: float = 20.0,
    pad_db: float = 3.0,
) -> tuple[float, float] | None:
    finite = np.asarray(values, dtype=float).ravel()
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return None

    low, high = np.nanpercentile(finite, [lower_percentile, upper_percentile])
    low = float(low)
    high = float(high)
    if high - low < min_span_db:
        center = (low + high) / 2.0
        low = center - min_span_db / 2.0
        high = center + min_span_db / 2.0
    return low - pad_db, high + pad_db


def _resolve_default_db_range(
    values: np.ndarray,
    requested_range: tuple[float, float],
    default_range: tuple[float, float],
) -> tuple[float, float]:
    if requested_range != default_range:
        return requested_range

    auto_range = _robust_db_range(values)
    if auto_range is None:
        return requested_range

    robust_range = _robust_db_range(values, pad_db=0.0)
    if robust_range is None:
        return requested_range
    requested_min, requested_max = requested_range
    robust_min, robust_max = robust_range
    if requested_min <= robust_min and requested_max >= robust_max:
        return requested_range
    return auto_range


def compute_psd(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    channel = runtime.load_channel(node.source_refs["lfp"])
    _, values = runtime.load_channel_fragment(node.source_refs["lfp"])
    freq, power = signal.welch(values, **_welch_kwargs(channel.sampling_rate_hz, params))
    min_freq_hz = float(params.get("min_freq_hz", 0.0))
    max_freq_hz = float(params["max_freq_hz"])
    mask = (freq >= min_freq_hz) & (freq <= max_freq_hz)
    power_db = 10.0 * np.log10(np.maximum(power[mask], 1e-12))
    y_range = _resolve_default_db_range(
        power_db,
        (float(params["y_min_db"]), float(params["y_max_db"])),
        PSD_DEFAULT_Y_RANGE,
    )
    frame = pd.DataFrame(
        {
            "frequency_hz": freq[mask],
            "power": power[mask],
            "power_db": power_db,
            "source_id": node.source_refs["lfp"],
        }
    )
    return AnalysisResult(
        node_id=node.node_id,
        title=f"PSD - {node.label}",
        kind="line",
        x_label="Frequency (Hz)",
        y_label="Power (dB)",
        series=[PlotSeries(label=node.label, x=frame["frequency_hz"].to_numpy(), y=frame["power_db"].to_numpy())],
        export_table=frame,
        meta={"y_range": y_range},
    )


def compute_spectrogram(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    channel = runtime.load_channel(node.source_refs["lfp"])
    _, values = runtime.load_channel_fragment(node.source_refs["lfp"])
    freq, times, power = signal.spectrogram(values, **_spectrogram_kwargs(channel.sampling_rate_hz, params))
    min_freq_hz = float(params.get("min_freq_hz", 0.0))
    max_freq_hz = float(params["max_freq_hz"])
    mask = (freq >= min_freq_hz) & (freq <= max_freq_hz)
    matrix = 10.0 * np.log10(np.maximum(power[mask], 1e-12))
    filtered_freq = freq[mask]
    color_range = _resolve_default_db_range(
        matrix,
        (float(params["vmin_db"]), float(params["vmax_db"])),
        SPECTROGRAM_DEFAULT_COLOR_RANGE,
    )
    export = pd.DataFrame(matrix, index=np.round(filtered_freq, 6), columns=np.round(times, 6))
    export.index.name = "frequency_hz"
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Spectrogram - {node.label}",
        kind="heatmap",
        x_label="Time (s)",
        y_label="Frequency (Hz)",
        color_label="Power (dB)",
        image=matrix,
        image_x=times,
        image_y=filtered_freq,
        export_table=export,
        meta={"vmin": color_range[0], "vmax": color_range[1]},
    )


def compute_pac(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    channel = runtime.load_channel(node.source_refs["lfp"])
    pac_state = _shared_pac_state(runtime, node, params, channel.sampling_rate_hz)
    export = pd.DataFrame(
        pac_state["matrix"],
        index=np.round(pac_state["amp_centers"], 6),
        columns=np.round(pac_state["phase_centers"], 6),
    )
    export.index.name = "amplitude_frequency_hz"
    export.columns.name = "phase_frequency_hz"
    peak_meta = _pac_peak_meta(pac_state)

    return AnalysisResult(
        node_id=node.node_id,
        title=f"PAC - {node.label}",
        kind="heatmap",
        x_label="Phase Frequency (Hz)",
        y_label="Amplitude Frequency (Hz)",
        color_label="Modulation Index",
        image=pac_state["matrix"],
        image_x=pac_state["phase_centers"],
        image_y=pac_state["amp_centers"],
        export_table=export,
        meta={
            **peak_meta,
            "vmin": 0.0,
            "vmax": peak_meta["peak_mi"] if peak_meta["peak_mi"] > 0 else None,
        },
    )


def compute_pac_polar(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    channel = runtime.load_channel(node.source_refs["lfp"])
    pac_state = _shared_pac_state(runtime, node, params, channel.sampling_rate_hz)
    peak_row, peak_col = pac_state["peak_indices"]
    peak_amp_hz = float(pac_state["amp_centers"][peak_row])
    peak_phase_hz = float(pac_state["phase_centers"][peak_col])
    mean_amplitudes = _phase_binned_means(
        pac_state["phase_lookup"][peak_phase_hz],
        pac_state["amplitude_lookup"][peak_amp_hz],
        pac_state["phase_edges"],
    )
    phase_left_rad = pac_state["phase_edges"][:-1]
    phase_right_rad = pac_state["phase_edges"][1:]
    phase_center_rad = (phase_left_rad + phase_right_rad) / 2.0
    export = pd.DataFrame(
        {
            "phase_left_rad": phase_left_rad,
            "phase_right_rad": phase_right_rad,
            "phase_center_rad": phase_center_rad,
            "mean_amplitude": mean_amplitudes,
            "peak_phase_frequency_hz": peak_phase_hz,
            "peak_amplitude_frequency_hz": peak_amp_hz,
            "source_id": node.source_refs["lfp"],
        }
    )
    peak_meta = _pac_peak_meta(pac_state)
    return AnalysisResult(
        node_id=node.node_id,
        title=f"PAC Polar - {node.label}",
        kind="polar",
        color_label="Mean Amplitude",
        series=[PlotSeries(label=node.label, x=phase_center_rad, y=mean_amplitudes)],
        export_table=export,
        meta=peak_meta,
    )


def compute_bandpass_preview(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    channel = runtime.load_channel(node.source_refs["lfp"])
    times, values = runtime.load_channel_fragment(node.source_refs["lfp"])
    if times.size == 0:
        return AnalysisResult(
            node_id=node.node_id,
            title=f"Band-pass Preview - {node.label}",
            kind="message",
            message="No LFP fragment available.",
        )
    mask = times <= times[0] + float(params["preview_duration_s"])
    preview_times = times[mask]
    preview_values = values[mask]
    band_specs = _bandpass_preview_specs(channel.sampling_rate_hz, params)
    filtered_traces = [
        (
            label,
            low_hz,
            high_hz,
            bandpass(
                preview_values,
                fs=channel.sampling_rate_hz,
                low_hz=low_hz,
                high_hz=high_hz,
                order=int(params["order"]),
            ),
        )
        for label, low_hz, high_hz in band_specs
    ]
    y_limit = max(float(np.max(np.abs(trace))) for _, _, _, trace in filtered_traces)
    y_limit = y_limit if y_limit > 0 else 1.0

    panels = [
        AnalysisResult(
            node_id=f"{node.node_id}:{index}",
            title=f"{label} ({low_hz:.1f}-{high_hz:.1f} Hz)",
            kind="line",
            x_label="Time (s)",
            y_label="Amplitude",
            series=[PlotSeries(label=label, x=preview_times, y=trace)],
            export_table=pd.DataFrame(
                {
                    "time_s": preview_times,
                    "amplitude": trace,
                    "low_hz": low_hz,
                    "high_hz": high_hz,
                    "band_label": label,
                    "source_id": node.source_refs["lfp"],
                }
            ),
            meta={"y_range": (-y_limit, y_limit)},
        )
        for index, (label, low_hz, high_hz, trace) in enumerate(filtered_traces, start=1)
    ]
    frame = pd.concat(
        [panel.export_table.assign(panel=panel.title) for panel in panels],
        ignore_index=True,
    )
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Band-pass Preview - {node.label}",
        kind="composite",
        export_table=frame,
        panels=panels,
        meta={"layout": {"rows": 3, "cols": 2}},
    )


def compute_band_power(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    channel = runtime.load_channel(node.source_refs["lfp"])
    _, values = runtime.load_channel_fragment(node.source_refs["lfp"])
    freq, times, power = signal.spectrogram(values, **_spectrogram_kwargs(channel.sampling_rate_hz, params))
    mask = (freq >= float(params["low_hz"])) & (freq <= float(params["high_hz"]))
    band_power = power[mask].mean(axis=0)
    frame = pd.DataFrame({"time_s": times, "power": band_power, "source_id": node.source_refs["lfp"]})
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Band Power - {node.label}",
        kind="line",
        x_label="Time (s)",
        y_label="Power",
        series=[PlotSeries(label=node.label, x=times, y=band_power)],
        export_table=frame,
    )


def _frequency_grid(start_hz: float, stop_hz: float, step_hz: float) -> np.ndarray:
    return np.arange(start_hz, stop_hz + step_hz * 0.5, step_hz, dtype=float)


def _shared_pac_state(runtime: AnalysisRuntime, node: AnalysisNode, params: dict, sampling_rate_hz: float) -> dict[str, object]:
    cache_param_keys = (
        "phase_min_hz",
        "phase_max_hz",
        "phase_step_hz",
        "phase_bandwidth_hz",
        "amp_min_hz",
        "amp_max_hz",
        "amp_step_hz",
        "amp_bandwidth_hz",
        "phase_bins",
        "filter_order",
    )
    cache_key = (
        "lfp",
        "pac_state",
        node.source_refs["lfp"],
        float(sampling_rate_hz),
        tuple((key, params[key]) for key in cache_param_keys),
    )

    def factory() -> dict[str, object]:
        channel = runtime.load_channel(node.source_refs["lfp"])
        _, values = runtime.load_channel_fragment(node.source_refs["lfp"])
        return _compute_pac_state(values, channel.sampling_rate_hz, params)

    return runtime.cache_get_or_create(cache_key, factory)


def _bandpass_preview_specs(sampling_rate_hz: float, params: dict) -> list[tuple[str, float, float]]:
    requested = [
        ("Custom", float(params["low_hz"]), float(params["high_hz"])),
        ("Delta", 0.5, 4.0),
        ("Theta", 4.0, 8.0),
        ("Alpha", 8.0, 13.0),
        ("Beta", 13.0, 30.0),
        ("Gamma", 30.0, 80.0),
    ]
    nyquist_hz = float(sampling_rate_hz) / 2.0
    resolved: list[tuple[str, float, float]] = []
    for label, low_hz, high_hz in requested:
        clipped_high_hz = min(high_hz, nyquist_hz * 0.98)
        if low_hz >= clipped_high_hz:
            continue
        resolved.append((label, low_hz, clipped_high_hz))
    return resolved


def _compute_pac_state(values: np.ndarray, sampling_rate_hz: float, params: dict) -> dict[str, object]:
    values = signal.detrend(np.asarray(values, dtype=float))
    phase_centers = _frequency_grid(
        float(params["phase_min_hz"]),
        float(params["phase_max_hz"]),
        float(params["phase_step_hz"]),
    )
    amp_centers = _frequency_grid(
        float(params["amp_min_hz"]),
        float(params["amp_max_hz"]),
        float(params["amp_step_hz"]),
    )
    phase_half_band = float(params["phase_bandwidth_hz"]) / 2.0
    amp_half_band = float(params["amp_bandwidth_hz"]) / 2.0
    filter_order = int(params["filter_order"])
    phase_edges = np.linspace(-np.pi, np.pi, int(params["phase_bins"]) + 1)

    phase_lookup = {
        center_hz: np.angle(
            signal.hilbert(
                bandpass(
                    values,
                    fs=sampling_rate_hz,
                    low_hz=center_hz - phase_half_band,
                    high_hz=center_hz + phase_half_band,
                    order=filter_order,
                )
            )
        )
        for center_hz in phase_centers
    }
    amplitude_lookup = {
        center_hz: np.abs(
            signal.hilbert(
                bandpass(
                    values,
                    fs=sampling_rate_hz,
                    low_hz=center_hz - amp_half_band,
                    high_hz=center_hz + amp_half_band,
                    order=filter_order,
                )
            )
        )
        for center_hz in amp_centers
    }

    matrix = np.zeros((len(amp_centers), len(phase_centers)), dtype=float)
    for row_index, amp_center_hz in enumerate(amp_centers):
        amplitude_envelope = amplitude_lookup[amp_center_hz]
        for column_index, phase_center_hz in enumerate(phase_centers):
            matrix[row_index, column_index] = _tort_modulation_index(
                phase_lookup[phase_center_hz],
                amplitude_envelope,
                phase_edges,
            )

    peak_indices = np.unravel_index(np.nanargmax(matrix), matrix.shape)
    return {
        "phase_centers": phase_centers,
        "amp_centers": amp_centers,
        "phase_edges": phase_edges,
        "phase_lookup": phase_lookup,
        "amplitude_lookup": amplitude_lookup,
        "matrix": matrix,
        "peak_indices": peak_indices,
    }


def _pac_peak_meta(pac_state: dict[str, object]) -> dict[str, float]:
    peak_row, peak_col = pac_state["peak_indices"]
    matrix = pac_state["matrix"]
    amp_centers = pac_state["amp_centers"]
    phase_centers = pac_state["phase_centers"]
    return {
        "peak_phase_hz": float(phase_centers[peak_col]),
        "peak_amp_hz": float(amp_centers[peak_row]),
        "peak_mi": float(matrix[peak_row, peak_col]),
    }


def _phase_binned_means(
    phase_angles: np.ndarray,
    amplitude_envelope: np.ndarray,
    phase_edges: np.ndarray,
) -> np.ndarray:
    bin_ids = np.digitize(phase_angles, phase_edges, right=False) - 1
    bin_ids = np.clip(bin_ids, 0, len(phase_edges) - 2)
    mean_amplitudes = np.zeros(len(phase_edges) - 1, dtype=float)

    for bin_index in range(len(mean_amplitudes)):
        in_bin = amplitude_envelope[bin_ids == bin_index]
        if in_bin.size:
            mean_amplitudes[bin_index] = float(np.mean(in_bin))
    return mean_amplitudes


def _tort_modulation_index(
    phase_angles: np.ndarray,
    amplitude_envelope: np.ndarray,
    phase_edges: np.ndarray,
) -> float:
    mean_amplitudes = _phase_binned_means(phase_angles, amplitude_envelope, phase_edges)
    total = float(np.sum(mean_amplitudes))
    if total <= 0.0:
        return 0.0

    distribution = mean_amplitudes / total
    non_zero = distribution[distribution > 0.0]
    entropy = -float(np.sum(non_zero * np.log(non_zero)))
    return max(0.0, (np.log(len(mean_amplitudes)) - entropy) / np.log(len(mean_amplitudes)))
