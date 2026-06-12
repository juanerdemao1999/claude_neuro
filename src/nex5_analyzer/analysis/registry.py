from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Literal

from ..models import AnalysisNode, AnalysisResult
from . import lfp, lfp_lfp, spike, spike_lfp
from .runtime import AnalysisRuntime

BuildMode = Literal[
    "lfp_each",
    "spike_each",
    "spike_summary_and_each",
    "spike_pair",
    "lfp_pair",
    "session_single",
    "spike_lfp_pair",
    "spike_lfp_lfp_each",
]
AnalysisScope = Literal["lfp", "spike", "lfp_lfp", "spike_lfp"]
ComputeHandler = Callable[[AnalysisRuntime, AnalysisNode, dict[str, Any]], AnalysisResult]


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    key: str
    label: str
    kind: str
    minimum: float | int | None = None
    maximum: float | int | None = None
    step: float | int | None = None
    choices: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class AnalysisDefinition:
    key: str
    label: str
    scope: AnalysisScope
    build_mode: BuildMode
    default_params: dict[str, Any]
    parameter_specs: tuple[ParameterSpec, ...]
    handler: ComputeHandler
    enabled_by_default: bool = True


WINDOW_FUNCTION_CHOICES = ("hann", "hamming", "blackman", "boxcar")
WELCH_AVERAGE_CHOICES = ("mean", "median")
COLORMAP_CHOICES = ("mako", "viridis", "magma", "rocket", "crest", "icefire")
DETREND_CHOICES = ("none", "constant", "linear")
SPECTRUM_SCALING_CHOICES = ("density", "spectrum")
POLAR_ZERO_LOCATION_CHOICES = ("N", "E", "S", "W")
POLAR_DIRECTION_CHOICES = ("clockwise", "counterclockwise")
POPULATION_SORT_CHOICES = ("phase_desc", "phase_asc", "spike_count_desc", "channel_then_unit")
WAVEFORM_SUMMARY_FEATURE_CHOICES = (
    "half_width_ms",
    "firing_rate_hz",
    "trough_to_peak_ms",
    "snr",
    "peak_to_trough_ratio",
    "peak_amplitude",
    "trough_amplitude",
    "spike_count",
)

PLOT_AXIS_DEFAULTS = {
    "plot_use_custom_x_range": False,
    "plot_x_min": 0.0,
    "plot_x_max": 1.0,
    "plot_use_custom_y_range": False,
    "plot_y_min": 0.0,
    "plot_y_max": 1.0,
}
PLOT_AXIS_PARAMETER_SPECS = (
    ParameterSpec("plot_use_custom_x_range", "Custom X Range", "bool"),
    ParameterSpec("plot_x_min", "X Min", "float", -1_000_000.0, 1_000_000.0, 0.1),
    ParameterSpec("plot_x_max", "X Max", "float", -1_000_000.0, 1_000_000.0, 0.1),
    ParameterSpec("plot_use_custom_y_range", "Custom Y Range", "bool"),
    ParameterSpec("plot_y_min", "Y Min", "float", -1_000_000.0, 1_000_000.0, 0.1),
    ParameterSpec("plot_y_max", "Y Max", "float", -1_000_000.0, 1_000_000.0, 0.1),
)

ANNOTATION_STYLE_DEFAULTS = {
    "plot_show_metrics_box": True,
}
ANNOTATION_STYLE_PARAMETER_SPECS = (
    ParameterSpec("plot_show_metrics_box", "Show Metrics Box", "bool"),
)

LINE_STYLE_DEFAULTS = {
    **PLOT_AXIS_DEFAULTS,
    "plot_show_legend": True,
    "plot_line_width": 2.2,
}
LINE_STYLE_PARAMETER_SPECS = (
    *PLOT_AXIS_PARAMETER_SPECS,
    ParameterSpec("plot_show_legend", "Show Legend", "bool"),
    ParameterSpec("plot_line_width", "Line Width", "float", 0.2, 20.0, 0.1),
)

SCATTER_STYLE_DEFAULTS = {
    **PLOT_AXIS_DEFAULTS,
    "plot_show_legend": True,
    "plot_marker_size": 55.0,
}
SCATTER_STYLE_PARAMETER_SPECS = (
    *PLOT_AXIS_PARAMETER_SPECS,
    ParameterSpec("plot_show_legend", "Show Legend", "bool"),
    ParameterSpec("plot_marker_size", "Marker Size", "float", 4.0, 500.0, 1.0),
)

SCATTER3D_STYLE_DEFAULTS = {
    **SCATTER_STYLE_DEFAULTS,
    "plot_view_elev": 18.0,
    "plot_view_azim": -52.0,
}
SCATTER3D_STYLE_PARAMETER_SPECS = (
    *SCATTER_STYLE_PARAMETER_SPECS,
    ParameterSpec("plot_view_elev", "View Elevation", "float", -90.0, 90.0, 1.0),
    ParameterSpec("plot_view_azim", "View Azimuth", "float", -180.0, 180.0, 1.0),
)

WAVEFORM_SUMMARY_DEFAULT_PARAMS = {
    "summary_max_units": 250,
    "summary_x_feature": "half_width_ms",
    "summary_y_feature": "firing_rate_hz",
    "summary_z_feature": "trough_to_peak_ms",
    "cluster_seed": 7,
}
WAVEFORM_SUMMARY_PARAMETER_SPECS = (
    ParameterSpec("summary_max_units", "Max Units", "int", 2, 5000, 1),
    ParameterSpec("summary_x_feature", "X Feature", "choice", choices=WAVEFORM_SUMMARY_FEATURE_CHOICES),
    ParameterSpec("summary_y_feature", "Y Feature", "choice", choices=WAVEFORM_SUMMARY_FEATURE_CHOICES),
    ParameterSpec("summary_z_feature", "Z Feature", "choice", choices=WAVEFORM_SUMMARY_FEATURE_CHOICES),
    ParameterSpec("cluster_seed", "Cluster Seed", "int", 0, 1_000_000, 1),
)

HEATMAP_STYLE_DEFAULTS = {
    **PLOT_AXIS_DEFAULTS,
    "plot_use_custom_color_range": False,
    "plot_color_min": 0.0,
    "plot_color_max": 1.0,
    "plot_show_colorbar": True,
    "plot_colormap": "mako",
}
HEATMAP_STYLE_PARAMETER_SPECS = (
    *PLOT_AXIS_PARAMETER_SPECS,
    ParameterSpec("plot_use_custom_color_range", "Custom Color Range", "bool"),
    ParameterSpec("plot_color_min", "Color Min", "float", -1_000_000.0, 1_000_000.0, 0.1),
    ParameterSpec("plot_color_max", "Color Max", "float", -1_000_000.0, 1_000_000.0, 0.1),
    ParameterSpec("plot_show_colorbar", "Show Colorbar", "bool"),
    ParameterSpec("plot_colormap", "Colormap", "choice", choices=COLORMAP_CHOICES),
)

PHASE_RASTER_STYLE_DEFAULTS = {
    **PLOT_AXIS_DEFAULTS,
    "plot_line_width": 2.2,
    "plot_marker_halfwidth_deg": 8.0,
    "plot_cycle_line_alpha": 0.7,
    "plot_wave_overlay": True,
    "plot_wave_overlay_alpha": 0.85,
}
PHASE_RASTER_STYLE_PARAMETER_SPECS = (
    *PLOT_AXIS_PARAMETER_SPECS,
    ParameterSpec("plot_line_width", "Line Width", "float", 0.2, 20.0, 0.1),
    ParameterSpec("plot_marker_halfwidth_deg", "Marker Halfwidth (deg)", "float", 1.0, 90.0, 1.0),
    ParameterSpec("plot_cycle_line_alpha", "Cycle Line Alpha", "float", 0.0, 1.0, 0.05),
    ParameterSpec("plot_wave_overlay", "Show Wave Overlay", "bool"),
    ParameterSpec("plot_wave_overlay_alpha", "Wave Overlay Alpha", "float", 0.0, 1.0, 0.05),
)

POLAR_STYLE_DEFAULTS = {
    **PLOT_AXIS_DEFAULTS,
    "plot_line_width": 0.8,
    "plot_polar_zero_location": "N",
    "plot_polar_direction": "clockwise",
    "plot_polar_tick_step_deg": 45,
    "plot_show_polar_grid": True,
}
POLAR_STYLE_PARAMETER_SPECS = (
    *PLOT_AXIS_PARAMETER_SPECS,
    ParameterSpec("plot_line_width", "Edge Width", "float", 0.2, 20.0, 0.1),
    ParameterSpec("plot_polar_zero_location", "Zero Location", "choice", choices=POLAR_ZERO_LOCATION_CHOICES),
    ParameterSpec("plot_polar_direction", "Polar Direction", "choice", choices=POLAR_DIRECTION_CHOICES),
    ParameterSpec("plot_polar_tick_step_deg", "Angle Tick Step", "int", 15, 180, 15),
    ParameterSpec("plot_show_polar_grid", "Show Polar Grid", "bool"),
)

SPECTROGRAM_WINDOW_DEFAULTS = {
    "window_function": "hann",
    "detrend_mode": "constant",
    "spectrum_scaling": "density",
}
SPECTROGRAM_WINDOW_PARAMETER_SPECS = (
    ParameterSpec("window_function", "Window Function", "choice", choices=WINDOW_FUNCTION_CHOICES),
    ParameterSpec("detrend_mode", "Detrend", "choice", choices=DETREND_CHOICES),
    ParameterSpec("spectrum_scaling", "Scaling", "choice", choices=SPECTRUM_SCALING_CHOICES),
)

# Magnitude-squared coherence is normalised, so the `spectrum_scaling`
# (density vs spectrum) choice has no effect on it. Coherence analyses use this
# reduced window control set instead of the full spectrogram one to avoid
# exposing a parameter that is silently ignored.
COHERENCE_WINDOW_DEFAULTS = {
    "window_function": "hann",
    "detrend_mode": "constant",
}
COHERENCE_WINDOW_PARAMETER_SPECS = (
    ParameterSpec("window_function", "Window Function", "choice", choices=WINDOW_FUNCTION_CHOICES),
    ParameterSpec("detrend_mode", "Detrend", "choice", choices=DETREND_CHOICES),
)

WELCH_STYLE_DEFAULTS = {
    **SPECTROGRAM_WINDOW_DEFAULTS,
    "welch_average": "mean",
}
WELCH_STYLE_PARAMETER_SPECS = (
    *SPECTROGRAM_WINDOW_PARAMETER_SPECS,
    ParameterSpec("welch_average", "PSD Average", "choice", choices=WELCH_AVERAGE_CHOICES),
)


def _merge_defaults(*groups: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for group in groups:
        merged.update(group)
    return merged


def _merge_specs(*groups: tuple[ParameterSpec, ...]) -> tuple[ParameterSpec, ...]:
    merged: list[ParameterSpec] = []
    seen: set[str] = set()
    for group in groups:
        for spec in group:
            if spec.key in seen:
                continue
            merged.append(spec)
            seen.add(spec.key)
    return tuple(merged)


PAC_DEFAULT_PARAMS = {
    "phase_min_hz": 2.0,
    "phase_max_hz": 12.0,
    "phase_step_hz": 2.0,
    "phase_bandwidth_hz": 2.0,
    "amp_min_hz": 30.0,
    "amp_max_hz": 120.0,
    "amp_step_hz": 10.0,
    # The amplitude filter bandwidth must be at least twice the highest phase
    # frequency so that the modulation side-bands are preserved (Aru et al.
    # 2015, Curr. Opin. Neurobiol. 31:51; Dvorak & Fenton 2014). With a phase
    # band up to 12 Hz the previous 20 Hz default was too narrow.
    "amp_bandwidth_hz": 30.0,
    "phase_bins": 18,
    "filter_order": 4,
}

PAC_PARAMETER_SPECS = (
    ParameterSpec("phase_min_hz", "Phase Min (Hz)", "float", 0.1, 500.0, 0.1),
    ParameterSpec("phase_max_hz", "Phase Max (Hz)", "float", 0.1, 500.0, 0.1),
    ParameterSpec("phase_step_hz", "Phase Step (Hz)", "float", 0.1, 100.0, 0.1),
    ParameterSpec("phase_bandwidth_hz", "Phase Bandwidth (Hz)", "float", 0.1, 100.0, 0.1),
    ParameterSpec("amp_min_hz", "Amp Min (Hz)", "float", 0.1, 1000.0, 0.1),
    ParameterSpec("amp_max_hz", "Amp Max (Hz)", "float", 0.1, 1000.0, 0.1),
    ParameterSpec("amp_step_hz", "Amp Step (Hz)", "float", 0.1, 200.0, 0.1),
    ParameterSpec("amp_bandwidth_hz", "Amp Bandwidth (Hz)", "float", 0.1, 200.0, 0.1),
    ParameterSpec("phase_bins", "Phase Bins", "int", 6, 72, 1),
    ParameterSpec("filter_order", "Order", "int", 1, 12, 1),
)

PHASE_LOCKING_DEFAULT_PARAMS = {"low_hz": 4.0, "high_hz": 12.0, "phase_bins": 18, "filter_order": 4}

PHASE_LOCKING_PARAMETER_SPECS = (
    ParameterSpec("low_hz", "Low (Hz)", "float", 0.1, 500.0, 0.1),
    ParameterSpec("high_hz", "High (Hz)", "float", 0.1, 500.0, 0.1),
    ParameterSpec("phase_bins", "Bins", "int", 6, 72, 1),
    ParameterSpec("filter_order", "Order", "int", 1, 12, 1),
)

SFC_SIGNIFICANCE_DEFAULT_PARAMS = {
    "max_freq_hz": 120.0,
    "nperseg": 1024,
    "noverlap": 768,
    "surrogate_runs": 200,
    "alpha": 0.05,
    "min_shift_s": 0.5,
}

SFC_SIGNIFICANCE_PARAMETER_SPECS = (
    ParameterSpec("max_freq_hz", "Max Freq (Hz)", "float", 1.0, 1000.0, 1.0),
    ParameterSpec("nperseg", "Window", "int", 64, 65536, 1),
    ParameterSpec("noverlap", "Overlap", "int", 0, 65535, 1),
    ParameterSpec("surrogate_runs", "Surrogates", "int", 8, 2000, 1),
    ParameterSpec("alpha", "Alpha", "float", 0.001, 0.5, 0.001),
    ParameterSpec("min_shift_s", "Min Shift (s)", "float", 0.01, 120.0, 0.01),
)

COHERENCE_REPORT_DEFAULT_PARAMS = {
    "window_ms": 100.0,
    "max_freq_hz": 120.0,
    "nperseg": 1024,
    "noverlap": 768,
    "low_hz": 4.0,
    "high_hz": 12.0,
    "phase_bins": 18,
    "filter_order": 4,
    "surrogate_runs": 200,
    "alpha": 0.05,
    "min_shift_s": 0.5,
}

COHERENCE_REPORT_PARAMETER_SPECS = (
    ParameterSpec("window_ms", "Window (ms)", "float", 1.0, 1000.0, 1.0),
    ParameterSpec("max_freq_hz", "Max Freq (Hz)", "float", 1.0, 1000.0, 1.0),
    ParameterSpec("nperseg", "Window", "int", 64, 65536, 1),
    ParameterSpec("noverlap", "Overlap", "int", 0, 65535, 1),
    ParameterSpec("low_hz", "Low (Hz)", "float", 0.1, 500.0, 0.1),
    ParameterSpec("high_hz", "High (Hz)", "float", 0.1, 500.0, 0.1),
    ParameterSpec("phase_bins", "Bins", "int", 6, 72, 1),
    ParameterSpec("filter_order", "Order", "int", 1, 12, 1),
    ParameterSpec("surrogate_runs", "Surrogates", "int", 8, 2000, 1),
    ParameterSpec("alpha", "Alpha", "float", 0.001, 0.5, 0.001),
    ParameterSpec("min_shift_s", "Min Shift (s)", "float", 0.01, 120.0, 0.01),
)


ANALYSIS_DEFINITIONS: tuple[AnalysisDefinition, ...] = (
    AnalysisDefinition(
        key="psd",
        label="PSD",
        scope="lfp",
        build_mode="lfp_each",
        default_params=_merge_defaults(
            {"min_freq_hz": 0.0, "max_freq_hz": 120.0, "nperseg": 1024, "noverlap": 768, "y_min_db": -70.0, "y_max_db": 0.0},
            WELCH_STYLE_DEFAULTS,
            LINE_STYLE_DEFAULTS,
        ),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("min_freq_hz", "Min Freq (Hz)", "float", 0.0, 1000.0, 0.1),
                ParameterSpec("max_freq_hz", "Max Freq (Hz)", "float", 1.0, 1000.0, 1.0),
                ParameterSpec("nperseg", "Window", "int", 64, 65536, 1),
                ParameterSpec("noverlap", "Overlap", "int", 0, 65535, 1),
                ParameterSpec("y_min_db", "Y Min (dB)", "float", -200.0, 100.0, 1.0),
                ParameterSpec("y_max_db", "Y Max (dB)", "float", -200.0, 100.0, 1.0),
            ),
            WELCH_STYLE_PARAMETER_SPECS,
            LINE_STYLE_PARAMETER_SPECS,
        ),
        handler=lfp.compute_psd,
    ),
    AnalysisDefinition(
        key="spectrogram",
        label="Spectrogram",
        scope="lfp",
        build_mode="lfp_each",
        default_params=_merge_defaults(
            {"min_freq_hz": 0.0, "max_freq_hz": 120.0, "nperseg": 1024, "noverlap": 768, "vmin_db": -80.0, "vmax_db": -20.0},
            SPECTROGRAM_WINDOW_DEFAULTS,
            HEATMAP_STYLE_DEFAULTS,
        ),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("min_freq_hz", "Min Freq (Hz)", "float", 0.0, 1000.0, 0.1),
                ParameterSpec("max_freq_hz", "Max Freq (Hz)", "float", 1.0, 1000.0, 1.0),
                ParameterSpec("nperseg", "Window", "int", 64, 65536, 1),
                ParameterSpec("noverlap", "Overlap", "int", 0, 65535, 1),
                ParameterSpec("vmin_db", "Color Min (dB)", "float", -200.0, 100.0, 1.0),
                ParameterSpec("vmax_db", "Color Max (dB)", "float", -200.0, 100.0, 1.0),
            ),
            SPECTROGRAM_WINDOW_PARAMETER_SPECS,
            HEATMAP_STYLE_PARAMETER_SPECS,
        ),
        handler=lfp.compute_spectrogram,
    ),
    AnalysisDefinition(
        key="pac",
        label="Phase-Amplitude Coupling",
        scope="lfp",
        build_mode="lfp_each",
        default_params=_merge_defaults(PAC_DEFAULT_PARAMS, HEATMAP_STYLE_DEFAULTS, ANNOTATION_STYLE_DEFAULTS),
        parameter_specs=_merge_specs(PAC_PARAMETER_SPECS, HEATMAP_STYLE_PARAMETER_SPECS, ANNOTATION_STYLE_PARAMETER_SPECS),
        handler=lfp.compute_pac,
    ),
    AnalysisDefinition(
        key="pac_polar",
        label="PAC Polar",
        scope="lfp",
        build_mode="lfp_each",
        default_params=_merge_defaults(PAC_DEFAULT_PARAMS, POLAR_STYLE_DEFAULTS, ANNOTATION_STYLE_DEFAULTS),
        parameter_specs=_merge_specs(PAC_PARAMETER_SPECS, POLAR_STYLE_PARAMETER_SPECS, ANNOTATION_STYLE_PARAMETER_SPECS),
        handler=lfp.compute_pac_polar,
    ),
    AnalysisDefinition(
        key="bandpass_preview",
        label="Band-pass Preview",
        scope="lfp",
        build_mode="lfp_each",
        default_params=_merge_defaults(
            {"low_hz": 0.0, "high_hz": 12.0, "order": 4, "preview_duration_s": 5.0},
            LINE_STYLE_DEFAULTS,
            ANNOTATION_STYLE_DEFAULTS,
        ),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("low_hz", "Low (Hz)", "float", 0.0, 500.0, 0.1),
                ParameterSpec("high_hz", "High (Hz)", "float", 0.1, 500.0, 0.1),
                ParameterSpec("order", "Order", "int", 1, 12, 1),
                ParameterSpec("preview_duration_s", "Preview (s)", "float", 0.2, 120.0, 0.1),
            ),
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=lfp.compute_bandpass_preview,
    ),
    AnalysisDefinition(
        key="band_power",
        label="Band Power vs Time",
        scope="lfp",
        build_mode="lfp_each",
        default_params=_merge_defaults(
            {"low_hz": 4.0, "high_hz": 12.0, "nperseg": 512, "noverlap": 384},
            SPECTROGRAM_WINDOW_DEFAULTS,
            LINE_STYLE_DEFAULTS,
            ANNOTATION_STYLE_DEFAULTS,
        ),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("low_hz", "Low (Hz)", "float", 0.0, 500.0, 0.1),
                ParameterSpec("high_hz", "High (Hz)", "float", 0.1, 500.0, 0.1),
                ParameterSpec("nperseg", "Window", "int", 64, 65536, 1),
                ParameterSpec("noverlap", "Overlap", "int", 0, 65535, 1),
            ),
            SPECTROGRAM_WINDOW_PARAMETER_SPECS,
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=lfp.compute_band_power,
    ),
    AnalysisDefinition(
        key="waveform_characterization",
        label="Waveform Characterization",
        scope="spike",
        build_mode="spike_summary_and_each",
        default_params=_merge_defaults(
            WAVEFORM_SUMMARY_DEFAULT_PARAMS,
            LINE_STYLE_DEFAULTS,
            SCATTER3D_STYLE_DEFAULTS,
            ANNOTATION_STYLE_DEFAULTS,
            {
                "waveform_max_display": 0,
                "waveform_individual_alpha": 0.15,
            },
        ),
        parameter_specs=_merge_specs(
            WAVEFORM_SUMMARY_PARAMETER_SPECS,
            LINE_STYLE_PARAMETER_SPECS,
            SCATTER3D_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
            (
                ParameterSpec("waveform_max_display", "Max Waveforms Display", "int", 0, 500, 1),
                ParameterSpec("waveform_individual_alpha", "Individual Alpha", "float", 0.0, 1.0, 0.05),
            ),
        ),
        handler=spike.compute_waveform_characterization,
    ),
    AnalysisDefinition(
        key="firing_rate",
        label="Firing Rate",
        scope="spike",
        build_mode="spike_each",
        default_params=_merge_defaults(
            {"bin_size_ms": 100.0, "smoothing_sigma_ms": 0.0},
            LINE_STYLE_DEFAULTS,
            ANNOTATION_STYLE_DEFAULTS,
        ),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("bin_size_ms", "Bin (ms)", "float", 1.0, 5000.0, 1.0),
                ParameterSpec("smoothing_sigma_ms", "Smooth Sigma (ms)", "float", 0.0, 5000.0, 1.0),
            ),
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike.compute_firing_rate,
    ),
    AnalysisDefinition(
        key="rate_power_metrics",
        label="Power Metrics of Spike Rate",
        scope="spike",
        build_mode="spike_each",
        default_params=_merge_defaults(
            {
                "bin_size_ms": 25.0,
                "smoothing_sigma_ms": 10.0,
                "max_freq_hz": 15.0,
                "nperseg": 64,
                "noverlap": 48,
                "vmin_db": -40.0,
                "vmax_db": 20.0,
            },
            WELCH_STYLE_DEFAULTS,
            LINE_STYLE_DEFAULTS,
            HEATMAP_STYLE_DEFAULTS,
            ANNOTATION_STYLE_DEFAULTS,
        ),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("bin_size_ms", "Bin (ms)", "float", 1.0, 5000.0, 1.0),
                ParameterSpec("smoothing_sigma_ms", "Smooth Sigma (ms)", "float", 0.0, 5000.0, 1.0),
                ParameterSpec("max_freq_hz", "Max Freq (Hz)", "float", 0.1, 500.0, 0.1),
                ParameterSpec("nperseg", "Window", "int", 8, 65536, 1),
                ParameterSpec("noverlap", "Overlap", "int", 0, 65535, 1),
                ParameterSpec("vmin_db", "Color Min (dB)", "float", -200.0, 200.0, 1.0),
                ParameterSpec("vmax_db", "Color Max (dB)", "float", -200.0, 200.0, 1.0),
            ),
            WELCH_STYLE_PARAMETER_SPECS,
            LINE_STYLE_PARAMETER_SPECS,
            HEATMAP_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike.compute_rate_power_metrics,
    ),
    AnalysisDefinition(
        key="isi",
        label="ISI",
        scope="spike",
        build_mode="spike_each",
        default_params=_merge_defaults({"bin_size_ms": 2.0, "max_interval_ms": 200.0}, LINE_STYLE_DEFAULTS, ANNOTATION_STYLE_DEFAULTS),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("bin_size_ms", "Bin (ms)", "float", 0.1, 1000.0, 0.1),
                ParameterSpec("max_interval_ms", "Max Interval (ms)", "float", 1.0, 5000.0, 1.0),
            ),
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike.compute_isi,
    ),
    AnalysisDefinition(
        key="autocorrelation",
        label="Autocorrelation",
        scope="spike",
        build_mode="spike_each",
        default_params=_merge_defaults({"bin_size_ms": 2.0, "max_lag_ms": 100.0}, LINE_STYLE_DEFAULTS, ANNOTATION_STYLE_DEFAULTS),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("bin_size_ms", "Bin (ms)", "float", 0.1, 100.0, 0.1),
                ParameterSpec("max_lag_ms", "Max Lag (ms)", "float", 1.0, 1000.0, 1.0),
            ),
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike.compute_autocorrelation,
    ),
    AnalysisDefinition(
        key="cross_correlation",
        label="Cross-correlation",
        scope="spike",
        build_mode="spike_pair",
        default_params=_merge_defaults({"bin_size_ms": 2.0, "max_lag_ms": 100.0}, LINE_STYLE_DEFAULTS, ANNOTATION_STYLE_DEFAULTS),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("bin_size_ms", "Bin (ms)", "float", 0.1, 100.0, 0.1),
                ParameterSpec("max_lag_ms", "Max Lag (ms)", "float", 1.0, 1000.0, 1.0),
            ),
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike.compute_cross_correlation,
    ),
    AnalysisDefinition(
        key="coherence",
        label="Pairwise Coherence",
        scope="lfp_lfp",
        build_mode="lfp_pair",
        default_params=_merge_defaults(
            {"max_freq_hz": 120.0, "nperseg": 1024, "noverlap": 768},
            COHERENCE_WINDOW_DEFAULTS,
            LINE_STYLE_DEFAULTS,
            ANNOTATION_STYLE_DEFAULTS,
        ),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("max_freq_hz", "Max Freq (Hz)", "float", 1.0, 1000.0, 1.0),
                ParameterSpec("nperseg", "Window", "int", 64, 65536, 1),
                ParameterSpec("noverlap", "Overlap", "int", 0, 65535, 1),
            ),
            COHERENCE_WINDOW_PARAMETER_SPECS,
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=lfp_lfp.compute_coherence,
    ),
    AnalysisDefinition(
        key="region_summary",
        label="Region Summary",
        scope="lfp_lfp",
        build_mode="session_single",
        default_params=_merge_defaults(
            {"max_freq_hz": 120.0, "nperseg": 1024, "noverlap": 768, "low_hz": 0.0, "high_hz": 120.0},
            COHERENCE_WINDOW_DEFAULTS,
            HEATMAP_STYLE_DEFAULTS,
            ANNOTATION_STYLE_DEFAULTS,
        ),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("max_freq_hz", "Max Freq (Hz)", "float", 1.0, 1000.0, 1.0),
                ParameterSpec("nperseg", "Window", "int", 64, 65536, 1),
                ParameterSpec("noverlap", "Overlap", "int", 0, 65535, 1),
                ParameterSpec("low_hz", "Mean Band Low (Hz)", "float", 0.0, 1000.0, 0.1),
                ParameterSpec("high_hz", "Mean Band High (Hz)", "float", 0.1, 1000.0, 0.1),
            ),
            COHERENCE_WINDOW_PARAMETER_SPECS,
            HEATMAP_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=lfp_lfp.compute_region_summary,
    ),
    AnalysisDefinition(
        key="sta",
        label="Spike-triggered Average",
        scope="spike_lfp",
        build_mode="spike_lfp_pair",
        default_params=_merge_defaults({"window_ms": 100.0}, LINE_STYLE_DEFAULTS, ANNOTATION_STYLE_DEFAULTS),
        parameter_specs=_merge_specs(
            (ParameterSpec("window_ms", "Window (ms)", "float", 1.0, 1000.0, 1.0),),
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike_lfp.compute_sta,
    ),
    AnalysisDefinition(
        key="sfc",
        label="Spike-field Coherence",
        scope="spike_lfp",
        build_mode="spike_lfp_pair",
        default_params=_merge_defaults(
            {"max_freq_hz": 120.0, "nperseg": 1024, "noverlap": 768},
            LINE_STYLE_DEFAULTS,
            ANNOTATION_STYLE_DEFAULTS,
        ),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("max_freq_hz", "Max Freq (Hz)", "float", 1.0, 1000.0, 1.0),
                ParameterSpec("nperseg", "Window", "int", 64, 65536, 1),
                ParameterSpec("noverlap", "Overlap", "int", 0, 65535, 1),
            ),
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike_lfp.compute_sfc,
    ),
    AnalysisDefinition(
        key="phase_locking",
        label="Spike-LFP Phase Locking",
        scope="spike_lfp",
        build_mode="spike_lfp_pair",
        default_params=_merge_defaults(PHASE_LOCKING_DEFAULT_PARAMS, LINE_STYLE_DEFAULTS, ANNOTATION_STYLE_DEFAULTS),
        parameter_specs=_merge_specs(
            PHASE_LOCKING_PARAMETER_SPECS,
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike_lfp.compute_phase_locking,
    ),
    AnalysisDefinition(
        key="phase_locking_polar",
        label="Spike-LFP Phase Locking (Polar)",
        scope="spike_lfp",
        build_mode="spike_lfp_pair",
        default_params=_merge_defaults(PHASE_LOCKING_DEFAULT_PARAMS, POLAR_STYLE_DEFAULTS, ANNOTATION_STYLE_DEFAULTS),
        parameter_specs=_merge_specs(
            PHASE_LOCKING_PARAMETER_SPECS,
            POLAR_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike_lfp.compute_phase_locking_polar,
    ),
    AnalysisDefinition(
        key="sfc_significance",
        label="Spike-field Coherence Significance",
        scope="spike_lfp",
        build_mode="spike_lfp_pair",
        default_params=_merge_defaults(SFC_SIGNIFICANCE_DEFAULT_PARAMS, LINE_STYLE_DEFAULTS, ANNOTATION_STYLE_DEFAULTS),
        parameter_specs=_merge_specs(
            SFC_SIGNIFICANCE_PARAMETER_SPECS,
            LINE_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike_lfp.compute_sfc_significance,
    ),
    AnalysisDefinition(
        key="coherence_report",
        label="Spike-LFP Coherence Report",
        scope="spike_lfp",
        build_mode="spike_lfp_pair",
        default_params=_merge_defaults(COHERENCE_REPORT_DEFAULT_PARAMS, LINE_STYLE_DEFAULTS, POLAR_STYLE_DEFAULTS, ANNOTATION_STYLE_DEFAULTS),
        parameter_specs=_merge_specs(
            COHERENCE_REPORT_PARAMETER_SPECS,
            LINE_STYLE_PARAMETER_SPECS,
            POLAR_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike_lfp.compute_coherence_report,
    ),
    AnalysisDefinition(
        key="population_coding",
        label="Population Coding",
        scope="spike_lfp",
        build_mode="spike_lfp_lfp_each",
        default_params=_merge_defaults(
            {
                "low_hz": 4.0,
                "high_hz": 12.0,
                "filter_order": 4,
                "max_units": 12,
                "max_cycles": 14,
                "min_spikes_per_unit": 5,
                "same_region_only": True,
                "unit_sort_mode": "phase_desc",
            },
            PHASE_RASTER_STYLE_DEFAULTS,
            ANNOTATION_STYLE_DEFAULTS,
        ),
        parameter_specs=_merge_specs(
            (
                ParameterSpec("low_hz", "Low (Hz)", "float", 0.1, 500.0, 0.1),
                ParameterSpec("high_hz", "High (Hz)", "float", 0.1, 500.0, 0.1),
                ParameterSpec("filter_order", "Order", "int", 1, 12, 1),
                ParameterSpec("max_units", "Max Units", "int", 1, 128, 1),
                ParameterSpec("max_cycles", "Max Cycles", "int", 1, 200, 1),
                ParameterSpec("min_spikes_per_unit", "Min Spikes", "int", 1, 10000, 1),
                ParameterSpec("same_region_only", "Same Region Only", "bool"),
                ParameterSpec("unit_sort_mode", "Unit Sort", "choice", choices=POPULATION_SORT_CHOICES),
            ),
            PHASE_RASTER_STYLE_PARAMETER_SPECS,
            ANNOTATION_STYLE_PARAMETER_SPECS,
        ),
        handler=spike_lfp.compute_population_coding,
    ),
)

_DEFINITION_BY_KEY = {definition.key: definition for definition in ANALYSIS_DEFINITIONS}


def get_analysis_definition(key: str) -> AnalysisDefinition:
    return _DEFINITION_BY_KEY[key]


def iter_analysis_definitions(scope: AnalysisScope | None = None) -> tuple[AnalysisDefinition, ...]:
    if scope is None:
        return ANALYSIS_DEFINITIONS
    return tuple(definition for definition in ANALYSIS_DEFINITIONS if definition.scope == scope)


def analysis_defaults_by_key() -> dict[str, dict[str, Any]]:
    return {definition.key: deepcopy(definition.default_params) for definition in ANALYSIS_DEFINITIONS}


def enabled_analyses_by_key() -> dict[str, bool]:
    return {definition.key: definition.enabled_by_default for definition in ANALYSIS_DEFINITIONS}


def parameter_specs_by_key() -> dict[str, list[ParameterSpec]]:
    return {definition.key: list(definition.parameter_specs) for definition in ANALYSIS_DEFINITIONS}
