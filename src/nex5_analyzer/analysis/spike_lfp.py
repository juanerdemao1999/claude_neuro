from __future__ import annotations

import neo
import numpy as np
import pandas as pd
import quantities as pq
from elephant.conversion import BinnedSpikeTrain
from elephant.phase_analysis import mean_phase_vector, spike_triggered_phase
from elephant.sta import spike_field_coherence, spike_triggered_average
from scipy import signal

from ..models import AnalysisNode, AnalysisResult, PlotSeries
from .common import bandpass
from .runtime import AnalysisRuntime

# Below this spike count the resultant-vector phase-locking estimates (PLV,
# Rayleigh statistic) are strongly biased and should be treated with caution.
# See Vinck et al. (2010), NeuroImage 51:112 and Zar (1999), Biostatistical
# Analysis, ch. 27.
MIN_RELIABLE_PHASE_SPIKES = 50


def compute_sta(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    state = _shared_sta_state(runtime, node, params)
    if state.get("error_message"):
        return AnalysisResult(
            node_id=node.node_id,
            title=f"STA - {node.label}",
            kind="message",
            message=str(state["error_message"]),
        )

    lags_ms = np.asarray(state["lags_ms"], dtype=float)
    mean_segment = np.asarray(state["mean_segment"], dtype=float)
    frame = pd.DataFrame({"lag_ms": lags_ms, "amplitude": mean_segment, "source_id": node.node_id})
    return AnalysisResult(
        node_id=node.node_id,
        title=f"STA - {node.label}",
        kind="line",
        x_label="Lag (ms)",
        y_label="Amplitude",
        series=[PlotSeries(label=node.label, x=lags_ms, y=mean_segment)],
        export_table=frame,
    )


def compute_sfc(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    state = _shared_sfc_state(runtime, node, params)
    if state.get("error_message"):
        return AnalysisResult(
            node_id=node.node_id,
            title=f"Spike-field Coherence - {node.label}",
            kind="message",
            message=str(state["error_message"]),
        )

    frame = state["frame"]
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Spike-field Coherence - {node.label}",
        kind="line",
        x_label="Frequency (Hz)",
        y_label="Coherence",
        series=[PlotSeries(label=node.label, x=frame["frequency_hz"].to_numpy(), y=frame["coherence"].to_numpy())],
        export_table=frame,
    )


def compute_sfc_significance(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    state = _shared_sfc_significance_state(runtime, node, params)
    if state.get("error_message"):
        return AnalysisResult(
            node_id=node.node_id,
            title=f"SFC Significance - {node.label}",
            kind="message",
            message=str(state["error_message"]),
        )

    frame = pd.DataFrame(
        {
            "frequency_hz": state["frequency_hz"],
            "negative_log10_pvalue": state["negative_log10_pvalue"],
            "negative_log10_threshold": state["negative_log10_threshold"],
            "coherence": state["coherence"],
            "source_id": node.node_id,
        }
    )
    return AnalysisResult(
        node_id=node.node_id,
        title=f"SFC Significance - {node.label}",
        kind="line",
        x_label="Frequency (Hz)",
        y_label="-log10(p)",
        series=[PlotSeries(label=node.label, x=state["frequency_hz"], y=state["negative_log10_pvalue"])],
        export_table=frame,
        meta={
            "reference_hlines": [
                {
                    "y": float(state["negative_log10_threshold"][0]),
                    "color": "#C44E52",
                    "linestyle": "--",
                    "linewidth": 1.4,
                }
            ],
            "peak_frequency_hz": float(state["peak_frequency_hz"]),
            "alpha": float(state["alpha"]),
        },
    )


def compute_phase_locking(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    state = _phase_locking_histogram_state(runtime, node, params)
    if state.get("error_message"):
        return AnalysisResult(
            node_id=node.node_id,
            title=f"Phase Locking - {node.label}",
            kind="message",
            message=str(state["error_message"]),
        )

    frame = pd.DataFrame(
        {
            "bin_left_rad": state["edges"][:-1],
            "bin_right_rad": state["edges"][1:],
            "count": state["counts"],
            "source_id": node.node_id,
        }
    )
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Phase Locking - {node.label}",
        kind="hist",
        x_label="Phase (rad)",
        y_label="Spike Count",
        series=[PlotSeries(label=node.label, x=state["edges"][:-1], y=state["counts"])],
        export_table=frame,
        meta={
            "mean_phase_rad": state["mean_angle"],
            "plv": state["plv"],
            "ppc": state["ppc"],
            "rayleigh_z": state["rayleigh_z"],
            "rayleigh_p": state["rayleigh_p"],
            "kappa": state["kappa"],
            "spike_count": state["spike_count"],
            "low_spike_warning": state["low_spike_warning"],
        },
    )


def compute_phase_locking_polar(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    state = _phase_locking_histogram_state(runtime, node, params)
    if state.get("error_message"):
        return AnalysisResult(
            node_id=node.node_id,
            title=f"Phase Locking (Polar) - {node.label}",
            kind="message",
            message=str(state["error_message"]),
        )

    centers = (state["edges"][:-1] + state["edges"][1:]) / 2.0
    frame = pd.DataFrame(
        {
            "phase_left_rad": state["edges"][:-1],
            "phase_right_rad": state["edges"][1:],
            "phase_center_rad": centers,
            "count": state["counts"],
            "source_id": node.node_id,
        }
    )
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Phase Locking (Polar) - {node.label}",
        kind="polar",
        export_table=frame,
        meta={
            "mean_phase_rad": state["mean_angle"],
            "plv": state["plv"],
            "ppc": state["ppc"],
            "rayleigh_z": state["rayleigh_z"],
            "rayleigh_p": state["rayleigh_p"],
            "kappa": state["kappa"],
            "spike_count": state["spike_count"],
            "low_spike_warning": state["low_spike_warning"],
        },
    )


def compute_coherence_report(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    panels = [
        compute_phase_locking_polar(runtime, node, params),
        compute_sfc_significance(runtime, node, params),
        compute_sta(runtime, node, params),
        compute_sfc(runtime, node, params),
    ]
    combined_export = _combine_panel_exports(panels)
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Spike-LFP Coherence Report - {node.label}",
        kind="composite",
        export_table=combined_export,
        panels=panels,
        meta={"layout": {"rows": 2, "cols": 2}},
    )


def compute_population_coding(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    channel = runtime.load_channel(node.source_refs["lfp"])
    times, values = runtime.load_channel_fragment(node.source_refs["lfp"])
    if times.size < 8:
        return AnalysisResult(
            node_id=node.node_id,
            title=f"Population Coding - {node.label}",
            kind="message",
            message="LFP fragment is too short for population coding.",
        )

    filtered = bandpass(
        values,
        fs=channel.sampling_rate_hz,
        low_hz=float(params["low_hz"]),
        high_hz=float(params["high_hz"]),
        order=int(params["filter_order"]),
    )
    analytic = signal.hilbert(filtered)
    wrapped_phase_rad = np.mod(np.angle(analytic), 2.0 * np.pi)
    unwrapped_phase_rad = np.unwrap(np.angle(analytic))
    lfp_channel = runtime.session.get_lfp_channel(node.source_refs["lfp"])

    candidate_units = list(runtime.session.spike_units)
    if bool(params.get("same_region_only")) and lfp_channel.region_scope is not None:
        candidate_units = [unit for unit in candidate_units if unit.region_scope == lfp_channel.region_scope]

    unit_events: list[dict[str, object]] = []
    min_spikes_per_unit = int(params["min_spikes_per_unit"])
    for unit in candidate_units:
        spike = runtime.load_spike(unit.variable_name)
        valid_spikes = spike.timestamps_s[(spike.timestamps_s >= times[0]) & (spike.timestamps_s <= times[-1])]
        if valid_spikes.size < min_spikes_per_unit:
            continue
        spike_unwrapped_phase_rad = np.interp(valid_spikes, times, unwrapped_phase_rad)
        spike_wrapped_phase_rad = np.mod(spike_unwrapped_phase_rad, 2.0 * np.pi)
        spike_phase_deg = np.degrees(spike_wrapped_phase_rad)
        spike_cycle_indices = np.floor((spike_unwrapped_phase_rad - unwrapped_phase_rad[0]) / (2.0 * np.pi)).astype(int)
        mean_phase_deg = float(np.degrees(np.mod(np.angle(np.mean(np.exp(1j * spike_wrapped_phase_rad))), 2.0 * np.pi)))
        unit_events.append(
            {
                "unit": unit,
                "spike_times_s": valid_spikes,
                "phase_deg": spike_phase_deg,
                "cycle_indices": spike_cycle_indices,
                "mean_phase_deg": mean_phase_deg,
            }
        )

    if not unit_events:
        return AnalysisResult(
            node_id=node.node_id,
            title=f"Population Coding - {node.label}",
            kind="message",
            message="No units met the minimum spike count for population coding.",
        )

    unit_events.sort(key=_population_unit_sort_key(str(params.get("unit_sort_mode", "phase_desc"))))
    selected_units = unit_events[: int(params["max_units"])]
    min_cycle = min(int(np.min(item["cycle_indices"])) for item in selected_units)
    max_cycle = min_cycle + int(params["max_cycles"]) - 1

    rows: list[dict[str, object]] = []
    total_units = len(selected_units)
    for index, item in enumerate(selected_units):
        unit = item["unit"]
        unit_order = total_units - index - 1
        spike_times_s = np.asarray(item["spike_times_s"], dtype=float)
        phase_deg = np.asarray(item["phase_deg"], dtype=float)
        spike_cycle_indices = np.asarray(item["cycle_indices"], dtype=int)
        visible = (spike_cycle_indices >= min_cycle) & (spike_cycle_indices <= max_cycle)
        for spike_time_s, phase_value_deg, cycle_index in zip(
            spike_times_s[visible],
            phase_deg[visible],
            spike_cycle_indices[visible],
            strict=False,
        ):
            rows.append(
                {
                    "unit_label": unit.display_name,
                    "unit_order": unit_order,
                    "cycle_index": int(cycle_index - min_cycle),
                    "phase_deg": float(phase_value_deg),
                    "x_deg": float((cycle_index - min_cycle) * 360.0 + phase_value_deg),
                    "spike_time_s": float(spike_time_s),
                    "mean_phase_deg": float(item["mean_phase_deg"]),
                    "subject": unit.subject or "",
                    "region": unit.region or "",
                    "region_label": unit.region_label,
                    "source_id": node.node_id,
                }
            )

    if not rows:
        return AnalysisResult(
            node_id=node.node_id,
            title=f"Population Coding - {node.label}",
            kind="message",
            message="No spikes fell inside the requested cycle window.",
        )

    frame = pd.DataFrame(rows).sort_values(["unit_order", "x_deg"]).reset_index(drop=True)
    displayed_cycles = int(frame["cycle_index"].max()) + 1
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Population Coding - {node.label}",
        kind="phase_raster",
        x_label="Theta Phase (deg, cumulative across cycles)",
        y_label="Unit",
        export_table=frame,
        meta={
            "displayed_cycles": displayed_cycles,
            "phase_reference_deg": np.degrees(np.mod(wrapped_phase_rad[0], 2.0 * np.pi)),
            "marker_halfwidth_deg": 8.0,
        },
    )


def _build_sta_state(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> dict[str, object]:
    channel = runtime.load_channel(node.source_refs["lfp"])
    spike = runtime.load_spike(node.source_refs["spike"])
    times, values = runtime.load_channel_fragment(node.source_refs["lfp"])
    if times.size == 0:
        return {"error_message": "No LFP fragment available."}

    aligned_spikes = _valid_spikes_for_fragment(spike.timestamps_s, times)
    if aligned_spikes.size == 0:
        return {"error_message": "No spikes overlap with the selected LFP fragment."}

    analog = _build_analog_signal(np.asarray(values, dtype=float), channel.sampling_rate_hz, float(times[0]))
    spiketrain = neo.SpikeTrain(np.sort(aligned_spikes) * pq.s, t_start=times[0] * pq.s, t_stop=times[-1] * pq.s)
    half_window_ms = float(params["window_ms"])
    result_sta = spike_triggered_average(
        analog,
        spiketrain,
        window=(-half_window_ms * pq.ms, half_window_ms * pq.ms),
    )

    mean_segment = np.asarray(result_sta.magnitude, dtype=float).squeeze()
    if mean_segment.size == 0 or not np.any(np.isfinite(mean_segment)):
        return {"error_message": "No spikes fell within the valid STA window for the selected fragment."}

    lags_ms = np.asarray(result_sta.times.rescale(pq.ms).magnitude, dtype=float)
    return {"lags_ms": lags_ms, "mean_segment": mean_segment}


def _shared_sta_state(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> dict[str, object]:
    cache_key = (
        "spike_lfp",
        "sta_state",
        node.source_refs["spike"],
        node.source_refs["lfp"],
        float(params["window_ms"]),
    )
    return runtime.cache_get_or_create(cache_key, lambda: _build_sta_state(runtime, node, params))


def _build_sfc_analog_state(runtime: AnalysisRuntime, node: AnalysisNode) -> dict[str, object]:
    channel = runtime.load_channel(node.source_refs["lfp"])
    times, values = runtime.load_channel_fragment(node.source_refs["lfp"])
    if times.size < 4:
        return {"error_message": "LFP fragment is too short for coherence."}

    return {
        "analog": _build_analog_signal(values, channel.sampling_rate_hz, float(times[0])),
        "times": times,
        "sampling_rate_hz": float(channel.sampling_rate_hz),
    }


def _shared_sfc_analog_state(runtime: AnalysisRuntime, node: AnalysisNode) -> dict[str, object]:
    cache_key = ("spike_lfp", "sfc_analog_state", node.source_refs["lfp"])
    return runtime.cache_get_or_create(cache_key, lambda: _build_sfc_analog_state(runtime, node))


def _build_sfc_state(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> dict[str, object]:
    analog_state = _shared_sfc_analog_state(runtime, node)
    if analog_state.get("error_message"):
        return {"error_message": analog_state["error_message"]}

    spike = runtime.load_spike(node.source_refs["spike"])
    times = np.asarray(analog_state["times"], dtype=float)
    valid_spikes = _valid_spikes_for_fragment(spike.timestamps_s, times)
    if valid_spikes.size == 0:
        return {"error_message": "No spikes overlap with the selected LFP fragment."}

    analog = analog_state["analog"]
    freq_hz, coherence_values = _coherence_curve_from_spikes(
        analog,
        valid_spikes,
        t_start_s=float(times[0]),
        t_stop_s=float(times[-1]),
        nperseg=int(params["nperseg"]),
        noverlap=int(params["noverlap"]),
        max_freq_hz=float(params["max_freq_hz"]),
    )
    frame = pd.DataFrame({"frequency_hz": freq_hz, "coherence": coherence_values, "source_id": node.node_id})
    return {
        "analog": analog,
        "frame": frame,
        "frequency_hz": freq_hz,
        "coherence": coherence_values,
        "valid_spikes": valid_spikes,
        "t_start_s": float(times[0]),
        "t_stop_s": float(times[-1]),
        "duration_s": float(times[-1] - times[0]),
        "sampling_rate_hz": float(analog_state["sampling_rate_hz"]),
    }


def _build_phase_signal_state(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> dict[str, object]:
    channel = runtime.load_channel(node.source_refs["lfp"])
    times, values = runtime.load_channel_fragment(node.source_refs["lfp"])
    if times.size == 0:
        return {"error_message": "No LFP fragment available."}

    filtered = bandpass(
        values,
        fs=channel.sampling_rate_hz,
        low_hz=float(params["low_hz"]),
        high_hz=float(params["high_hz"]),
        order=int(params["filter_order"]),
    )
    analytic = signal.hilbert(filtered)
    return {
        "analog": neo.AnalogSignal(
            analytic[:, np.newaxis],
            units="mV",
            sampling_rate=channel.sampling_rate_hz * pq.Hz,
            t_start=times[0] * pq.s,
        ),
        "times": times,
    }


def _shared_phase_signal_state(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> dict[str, object]:
    cache_key = (
        "spike_lfp",
        "phase_signal_state",
        node.source_refs["lfp"],
        float(params["low_hz"]),
        float(params["high_hz"]),
        int(params["filter_order"]),
    )
    return runtime.cache_get_or_create(cache_key, lambda: _build_phase_signal_state(runtime, node, params))


def _build_phase_locking_state(
    runtime: AnalysisRuntime,
    node: AnalysisNode,
    params: dict,
) -> dict[str, object]:
    phase_signal = _shared_phase_signal_state(runtime, node, params)
    if phase_signal.get("error_message"):
        return {"error_message": phase_signal["error_message"]}

    spike = runtime.load_spike(node.source_refs["spike"])
    times = np.asarray(phase_signal["times"], dtype=float)
    valid_spikes = _valid_spikes_for_fragment(spike.timestamps_s, times)
    if valid_spikes.size == 0:
        return {"error_message": "No spikes overlap with the selected LFP fragment."}
    spiketrain = neo.SpikeTrain(valid_spikes * pq.s, t_start=times[0] * pq.s, t_stop=times[-1] * pq.s)
    phases, _, _ = spike_triggered_phase(phase_signal["analog"], spiketrain, interpolate=True)
    phase_values = np.asarray(phases[0], dtype=float)
    return phase_locking_metrics(phase_values)


def _shared_sfc_state(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> dict[str, object]:
    cache_key = (
        "spike_lfp",
        "sfc_state",
        node.source_refs["spike"],
        node.source_refs["lfp"],
        float(params["max_freq_hz"]),
        int(params["nperseg"]),
        int(params["noverlap"]),
    )
    return runtime.cache_get_or_create(cache_key, lambda: _build_sfc_state(runtime, node, params))


def _build_sfc_significance_state(
    runtime: AnalysisRuntime,
    node: AnalysisNode,
    params: dict,
) -> dict[str, object]:
    state = _shared_sfc_state(runtime, node, params)
    if state.get("error_message"):
        return {"error_message": state["error_message"]}

    observed = state["coherence"]
    freq_hz = state["frequency_hz"]
    valid_spikes = state["valid_spikes"]
    t_start_s = state["t_start_s"]
    t_stop_s = state["t_stop_s"]
    analog = state["analog"]
    duration_s = state["duration_s"]
    surrogate_runs = int(params["surrogate_runs"])
    alpha = float(params["alpha"])

    surrogate_curves = np.zeros((surrogate_runs, len(observed)), dtype=float)
    rng = np.random.default_rng(20260327)
    min_shift_s = _effective_min_shift_s(float(params["min_shift_s"]), duration_s, state["sampling_rate_hz"])
    for index in range(surrogate_runs):
        shifted_spikes = _circular_shift_spikes(valid_spikes, min_shift_s, t_start_s, t_stop_s, rng)
        surrogate_curves[index] = _coherence_curve_from_spikes(
            analog,
            shifted_spikes,
            t_start_s=t_start_s,
            t_stop_s=t_stop_s,
            nperseg=int(params["nperseg"]),
            noverlap=int(params["noverlap"]),
            max_freq_hz=float(params["max_freq_hz"]),
        )[1]

    # Family-wise error control across frequencies via the max-statistic
    # permutation distribution (Nichols & Holmes 2002, Hum. Brain Mapp. 15:1).
    # Each surrogate contributes its single largest coherence across the whole
    # frequency axis; comparing the observed coherence at every frequency
    # against that null of maxima corrects for testing many frequencies at once.
    surrogate_max = surrogate_curves.max(axis=1) if surrogate_curves.size else np.zeros(0, dtype=float)
    pvalues = (1.0 + np.sum(surrogate_max[:, None] >= observed[None, :], axis=0)) / float(surrogate_runs + 1)
    negative_log10_pvalue = -np.log10(np.clip(pvalues, 1e-12, 1.0))
    negative_log10_threshold = np.full_like(negative_log10_pvalue, -np.log10(alpha), dtype=float)
    peak_index = int(np.argmax(observed)) if observed.size else 0
    return {
        "frequency_hz": freq_hz,
        "negative_log10_pvalue": negative_log10_pvalue,
        "negative_log10_threshold": negative_log10_threshold,
        "coherence": observed,
        "peak_frequency_hz": float(freq_hz[peak_index]) if freq_hz.size else float("nan"),
        "alpha": alpha,
    }


def _shared_sfc_significance_state(
    runtime: AnalysisRuntime,
    node: AnalysisNode,
    params: dict,
) -> dict[str, object]:
    cache_key = (
        "spike_lfp",
        "sfc_significance_state",
        node.source_refs["spike"],
        node.source_refs["lfp"],
        float(params["max_freq_hz"]),
        int(params["nperseg"]),
        int(params["noverlap"]),
        int(params["surrogate_runs"]),
        float(params["alpha"]),
        float(params["min_shift_s"]),
    )
    return runtime.cache_get_or_create(cache_key, lambda: _build_sfc_significance_state(runtime, node, params))


def _shared_phase_locking_state(
    runtime: AnalysisRuntime,
    node: AnalysisNode,
    params: dict,
) -> dict[str, object]:
    cache_key = (
        "spike_lfp",
        "phase_locking_state",
        node.source_refs["spike"],
        node.source_refs["lfp"],
        float(params["low_hz"]),
        float(params["high_hz"]),
        int(params["filter_order"]),
    )
    return runtime.cache_get_or_create(cache_key, lambda: _build_phase_locking_state(runtime, node, params))


def _phase_locking_histogram_state(
    runtime: AnalysisRuntime,
    node: AnalysisNode,
    params: dict,
) -> dict[str, object]:
    state = _shared_phase_locking_state(runtime, node, params)
    if state.get("error_message"):
        return {"error_message": state["error_message"]}

    counts, edges = np.histogram(state["phase_values"], bins=int(params["phase_bins"]), range=(-np.pi, np.pi))
    return {
        "counts": counts.astype(float),
        "edges": edges.astype(float),
        "mean_angle": float(state["mean_angle"]),
        "plv": float(state["plv"]),
        "ppc": float(state["ppc"]),
        "rayleigh_z": float(state["rayleigh_z"]),
        "rayleigh_p": float(state["rayleigh_p"]),
        "kappa": float(state["kappa"]),
        "spike_count": int(state["spike_count"]),
        "low_spike_warning": bool(state["low_spike_warning"]),
    }


def phase_locking_metrics(phase_values: np.ndarray) -> dict[str, object]:
    phase_array = np.asarray(phase_values, dtype=float)
    if phase_array.size == 0:
        return {"error_message": "No spikes overlap with the selected LFP fragment."}

    sample_count = int(phase_array.size)
    mean_angle, plv = mean_phase_vector(phase_array)
    rayleigh_z, rayleigh_p = _rayleigh_test(phase_array, float(plv))
    return {
        "phase_values": phase_array.astype(float),
        "mean_angle": float(mean_angle),
        "plv": float(plv),
        "ppc": float(_pairwise_phase_consistency(float(plv), sample_count)),
        "rayleigh_z": float(rayleigh_z),
        "rayleigh_p": float(rayleigh_p),
        "kappa": float(_estimate_kappa(float(plv), sample_count)),
        "spike_count": sample_count,
        "low_spike_warning": bool(sample_count < MIN_RELIABLE_PHASE_SPIKES),
    }


def _pairwise_phase_consistency(plv: float, sample_count: int) -> float:
    """Unbiased pairwise phase consistency (PPC0, Vinck et al. 2010).

    Unlike the resultant length (PLV), PPC is not biased by the number of
    spikes, so it is the recommended population/low-count phase-locking metric.
    """
    if sample_count < 2:
        return float("nan")
    resultant_length = float(plv)
    return float((sample_count * resultant_length * resultant_length - 1.0) / (sample_count - 1.0))


def _rayleigh_test(phase_values: np.ndarray, plv: float) -> tuple[float, float]:
    sample_count = int(np.asarray(phase_values, dtype=float).size)
    if sample_count <= 0:
        return 0.0, 1.0
    resultant_length = float(plv)
    rayleigh_z = sample_count * resultant_length * resultant_length
    # Zar (1999, eq. 27.4) / Berens (2009, CircStat `circ_rtest`) small-sample
    # expansion. The leading exp(-z) term equals the large-sample approximation
    # used previously; the higher-order terms correct the bias for small n.
    pvalue = np.exp(-rayleigh_z) * (
        1.0
        + (2.0 * rayleigh_z - rayleigh_z**2) / (4.0 * sample_count)
        - (
            24.0 * rayleigh_z
            - 132.0 * rayleigh_z**2
            + 76.0 * rayleigh_z**3
            - 9.0 * rayleigh_z**4
        )
        / (288.0 * sample_count**2)
    )
    return rayleigh_z, float(max(min(pvalue, 1.0), 0.0))


def _estimate_kappa(plv: float, sample_count: int) -> float:
    resultant_length = float(np.clip(plv, 0.0, 0.999999))
    if resultant_length < 1e-12:
        return 0.0
    if resultant_length < 0.53:
        kappa = 2.0 * resultant_length + resultant_length**3 + (5.0 * resultant_length**5) / 6.0
    elif resultant_length < 0.85:
        kappa = -0.4 + 1.39 * resultant_length + 0.43 / (1.0 - resultant_length)
    else:
        denominator = resultant_length**3 - 4.0 * resultant_length**2 + 3.0 * resultant_length
        if abs(denominator) < 1e-9:
            return float("inf")
        kappa = 1.0 / denominator

    if sample_count < 15 and kappa > 0.0:
        if kappa < 2.0:
            correction = 2.0 / max(sample_count * kappa, 1e-9)
            kappa = max(kappa - correction, 0.0)
        else:
            numerator = (sample_count - 1.0) ** 3 * kappa
            denominator = sample_count**3 + sample_count
            kappa = numerator / denominator
    return float(max(kappa, 0.0))


def _build_analog_signal(values: np.ndarray, sampling_rate_hz: float, t_start_s: float) -> neo.AnalogSignal:
    return neo.AnalogSignal(
        values[:, np.newaxis],
        units="mV",
        sampling_rate=sampling_rate_hz * pq.Hz,
        t_start=t_start_s * pq.s,
    )


def _valid_spikes_for_fragment(spike_times_s: np.ndarray, times: np.ndarray) -> np.ndarray:
    return spike_times_s[(spike_times_s >= times[0]) & (spike_times_s <= times[-1])]


def _coherence_curve_from_spikes(
    analog: neo.AnalogSignal,
    spike_times_s: np.ndarray,
    *,
    t_start_s: float,
    t_stop_s: float,
    nperseg: int,
    noverlap: int,
    max_freq_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    spiketrain = neo.SpikeTrain(np.sort(spike_times_s) * pq.s, t_start=t_start_s * pq.s, t_stop=t_stop_s * pq.s)
    binned_spiketrain = BinnedSpikeTrain(
        spiketrain,
        bin_size=analog.sampling_period,
        tolerance=None,
    )
    coherence, freq = spike_field_coherence(
        analog,
        binned_spiketrain,
        nperseg=nperseg,
        noverlap=noverlap,
    )
    freq_hz = np.asarray(getattr(freq, "magnitude", freq), dtype=float).squeeze()
    coherence_values = np.asarray(getattr(coherence, "magnitude", coherence), dtype=float).squeeze()
    mask = freq_hz <= max_freq_hz
    return freq_hz[mask], coherence_values[mask]


def _effective_min_shift_s(requested_min_shift_s: float, duration_s: float, sampling_rate_hz: float) -> float:
    floor_shift_s = max(1.0 / sampling_rate_hz, duration_s * 0.05)
    ceiling_shift_s = max(floor_shift_s, duration_s * 0.45)
    return min(max(requested_min_shift_s, floor_shift_s), ceiling_shift_s)


def _circular_shift_spikes(
    spike_times_s: np.ndarray,
    min_shift_s: float,
    t_start_s: float,
    t_stop_s: float,
    rng: np.random.Generator,
) -> np.ndarray:
    duration_s = max(t_stop_s - t_start_s, 1e-9)
    low = min_shift_s
    high = max(low + 1e-6, duration_s - min_shift_s)
    if high <= low:
        low = duration_s * 0.1
        high = max(low + 1e-6, duration_s * 0.9)
    shift_s = rng.uniform(low, high)
    shifted = ((spike_times_s - t_start_s + shift_s) % duration_s) + t_start_s
    upper_bound = np.nextafter(t_stop_s, t_start_s)
    return np.sort(np.clip(shifted, t_start_s, upper_bound))


def _combine_panel_exports(panels: list[AnalysisResult]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for panel in panels:
        if panel.export_table.empty:
            continue
        frame = panel.export_table.copy()
        frame.insert(0, "panel", panel.title)
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def _population_unit_sort_key(mode: str):
    def key(item: dict[str, object]) -> tuple[float, ...]:
        unit = item["unit"]
        spike_count = float(len(item["spike_times_s"]))
        mean_phase_deg = float(item["mean_phase_deg"])
        channel_id = float(getattr(unit, "channel_id", 0) or 0)
        unit_index = float(getattr(unit, "unit_index", 0) or 0)
        if mode == "phase_asc":
            return (mean_phase_deg, -spike_count, channel_id, unit_index)
        if mode == "spike_count_desc":
            return (-spike_count, -mean_phase_deg, channel_id, unit_index)
        if mode == "channel_then_unit":
            return (channel_id, unit_index, -spike_count, -mean_phase_deg)
        return (-mean_phase_deg, -spike_count, channel_id, unit_index)

    return key
