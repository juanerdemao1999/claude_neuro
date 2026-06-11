from __future__ import annotations

import numpy as np
import pandas as pd
from elephant.waveform_features import waveform_width
from scipy import signal

from ..models import AnalysisResult, PlotSeries


def waveform_width_ms(mean_waveform: np.ndarray, waveform_sample_rate_hz: float | None) -> float:
    if waveform_sample_rate_hz in (None, 0):
        return float("nan")
    return float(waveform_width(mean_waveform)) / float(waveform_sample_rate_hz) * 1000.0


def match_lengths(first: np.ndarray, second: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    length = min(len(first), len(second))
    return first[:length], second[:length]


def bandpass(values: np.ndarray, fs: float, low_hz: float, high_hz: float, order: int) -> np.ndarray:
    nyquist = fs / 2.0
    high_hz = min(high_hz, nyquist * 0.98)
    if low_hz <= 0.0:
        sos = signal.butter(order, high_hz, fs=fs, btype="lowpass", output="sos")
    else:
        sos = signal.butter(order, [low_hz, high_hz], fs=fs, btype="bandpass", output="sos")
    return signal.sosfiltfilt(sos, values)


def sparse_correlogram(first: np.ndarray, second: np.ndarray, edges: np.ndarray, exclude_zero: bool) -> np.ndarray:
    first = np.asarray(first, dtype=float)
    second = np.asarray(second, dtype=float)
    max_lag = float(np.max(np.abs(edges)))
    counts = np.zeros(len(edges) - 1, dtype=int)
    for spike_time in first:
        left = np.searchsorted(second, spike_time - max_lag, side="left")
        right = np.searchsorted(second, spike_time + max_lag, side="right")
        deltas = second[left:right] - spike_time
        if exclude_zero:
            deltas = deltas[np.abs(deltas) > 1e-12]
        hist, _ = np.histogram(deltas, bins=edges)
        counts += hist
    return counts


def correlogram_result(
    *,
    node_id: str,
    title: str,
    first: np.ndarray,
    second: np.ndarray,
    bin_size_s: float,
    max_lag_s: float,
    exclude_zero: bool,
    source_id: str,
) -> AnalysisResult:
    edges = np.arange(-max_lag_s, max_lag_s + bin_size_s, bin_size_s)
    counts = sparse_correlogram(first, second, edges, exclude_zero=exclude_zero)
    frame = pd.DataFrame({"lag_s": edges[:-1], "count": counts, "source_id": source_id})
    return AnalysisResult(
        node_id=node_id,
        title=title,
        kind="hist",
        x_label="Lag (s)",
        y_label="Count",
        series=[PlotSeries(label=title, x=edges[:-1], y=counts)],
        export_table=frame,
    )
