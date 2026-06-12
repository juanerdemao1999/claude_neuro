from __future__ import annotations

from fractions import Fraction
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import signal

from ..models import AnalysisNode, AnalysisResult, PlotSeries
from .common import match_lengths
from .runtime import AnalysisRuntime


def _resample_to_rate(values: np.ndarray, source_rate_hz: float, target_rate_hz: float) -> np.ndarray:
    """Resample a signal to ``target_rate_hz`` when it differs from its source rate.

    ``scipy.signal.coherence`` assumes both inputs share one sampling rate; if
    two LFP channels were digitised at different rates, simply truncating to a
    common sample count (as before) misaligns them in time and mislabels the
    frequency axis. Polyphase resampling onto the lower common rate keeps the
    two signals time-aligned and the coherence spectrum correct.
    """
    values = np.asarray(values, dtype=float)
    if source_rate_hz <= 0.0 or target_rate_hz <= 0.0 or values.size == 0:
        return values
    if np.isclose(source_rate_hz, target_rate_hz):
        return values
    ratio = Fraction(target_rate_hz / source_rate_hz).limit_denominator(1000)
    if ratio.numerator == 0 or ratio.denominator == 0:
        return values
    return np.asarray(signal.resample_poly(values, ratio.numerator, ratio.denominator), dtype=float)


def _coherence_kwargs(sample_rate_hz: float, params: dict) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "fs": sample_rate_hz,
        "nperseg": int(params["nperseg"]),
        "noverlap": int(params["noverlap"]),
    }
    if "window_function" in params:
        kwargs["window"] = str(params["window_function"])
    if "detrend_mode" in params:
        kwargs["detrend"] = False if str(params["detrend_mode"]) == "none" else str(params["detrend_mode"])
    return kwargs


def _build_pair_coherence_state(
    runtime: AnalysisRuntime,
    first_variable_name: str,
    second_variable_name: str,
    params: dict,
) -> dict[str, object]:
    first = runtime.load_channel(first_variable_name)
    second = runtime.load_channel(second_variable_name)
    _, a = runtime.load_channel_fragment(first_variable_name)
    _, b = runtime.load_channel_fragment(second_variable_name)
    common_rate_hz = min(first.sampling_rate_hz, second.sampling_rate_hz)
    a = _resample_to_rate(a, first.sampling_rate_hz, common_rate_hz)
    b = _resample_to_rate(b, second.sampling_rate_hz, common_rate_hz)
    a, b = match_lengths(a, b)
    freq, coh = signal.coherence(a, b, **_coherence_kwargs(common_rate_hz, params))
    mask = freq <= float(params["max_freq_hz"])
    return {
        "frequency_hz": freq[mask],
        "coherence": coh[mask],
        "mean_coherence": float(np.nanmean(coh[mask])) if np.any(mask) else float("nan"),
    }


def _band_mean_coherence(state: dict[str, object], low_hz: float, high_hz: float) -> float:
    freq = np.asarray(state["frequency_hz"], dtype=float)
    coherence = np.asarray(state["coherence"], dtype=float)
    band_mask = (freq >= low_hz) & (freq <= high_hz)
    if not np.any(band_mask):
        return float("nan")
    return float(np.nanmean(coherence[band_mask]))


def _shared_pair_coherence_state(
    runtime: AnalysisRuntime,
    first_variable_name: str,
    second_variable_name: str,
    params: dict,
) -> dict[str, object]:
    left, right = sorted((first_variable_name, second_variable_name))
    cache_key = (
        "lfp_lfp",
        "pair_coherence_state",
        left,
        right,
        float(params["max_freq_hz"]),
        int(params["nperseg"]),
        int(params["noverlap"]),
    )
    return runtime.cache_get_or_create(
        cache_key,
        lambda: _build_pair_coherence_state(runtime, first_variable_name, second_variable_name, params),
    )


def compute_coherence(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    state = _shared_pair_coherence_state(runtime, node.source_refs["lfp_a"], node.source_refs["lfp_b"], params)
    frame = pd.DataFrame(
        {
            "frequency_hz": np.asarray(state["frequency_hz"], dtype=float),
            "coherence": np.asarray(state["coherence"], dtype=float),
            "source_id": node.node_id,
        }
    )
    return AnalysisResult(
        node_id=node.node_id,
        title=f"Coherence - {node.label}",
        kind="line",
        x_label="Frequency (Hz)",
        y_label="Coherence",
        series=[PlotSeries(label=node.label, x=frame["frequency_hz"].to_numpy(), y=frame["coherence"].to_numpy())],
        export_table=frame,
    )


def compute_region_summary(runtime: AnalysisRuntime, node: AnalysisNode, params: dict) -> AnalysisResult:
    session = runtime.session
    mapped_channels = [channel for channel in session.lfp_channels if channel.region_scope is not None]
    if len(mapped_channels) < 2:
        return AnalysisResult(
            node_id=node.node_id,
            title="Region Summary",
            kind="message",
            message="Need at least two mapped LFP channels to build a region summary.",
        )

    low_hz = float(params.get("low_hz", 0.0))
    high_hz = float(params.get("high_hz", params["max_freq_hz"]))
    region_values: dict[tuple[str, str], list[float]] = {}
    for first, second in combinations(mapped_channels, 2):
        state = _shared_pair_coherence_state(runtime, first.variable_name, second.variable_name, params)
        key = tuple(sorted((first.region_label, second.region_label)))
        region_values.setdefault(key, []).append(_band_mean_coherence(state, low_hz, high_hz))

    regions = sorted({region for pair in region_values for region in pair})
    matrix = pd.DataFrame(np.nan, index=regions, columns=regions, dtype=float)
    for (left, right), values in region_values.items():
        value = float(np.mean(values))
        matrix.loc[left, right] = value
        matrix.loc[right, left] = value
    for index in range(min(matrix.shape)):
        matrix.iloc[index, index] = 1.0
    return AnalysisResult(
        node_id=node.node_id,
        title="LFP Region Summary",
        kind="heatmap",
        x_label="Region",
        y_label="Region",
        color_label="Mean Coherence",
        image=matrix.to_numpy(),
        image_x=np.arange(matrix.shape[1], dtype=float),
        image_y=np.arange(matrix.shape[0], dtype=float),
        export_table=matrix,
        meta={"x_tick_labels": list(matrix.columns), "y_tick_labels": list(matrix.index)},
    )
