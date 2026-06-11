from __future__ import annotations

from typing import Any

from ..models import AnalysisNode, SessionData
from .registry import (
    COLORMAP_CHOICES,
    DETREND_CHOICES,
    POLAR_DIRECTION_CHOICES,
    POLAR_ZERO_LOCATION_CHOICES,
    POPULATION_SORT_CHOICES,
    SPECTRUM_SCALING_CHOICES,
    WAVEFORM_SUMMARY_FEATURE_CHOICES,
    WELCH_AVERAGE_CHOICES,
    WINDOW_FUNCTION_CHOICES,
)


def validate_analysis_request(
    session: SessionData,
    node: AnalysisNode,
    params: dict[str, Any],
) -> dict[str, Any]:
    validated = dict(params)

    _require_positive(validated, "max_freq_hz")
    _require_non_negative(validated, "min_freq_hz")
    _require_positive(validated, "nperseg")
    _require_non_negative(validated, "noverlap")
    _require_non_negative(validated, "low_hz")
    _require_positive(validated, "high_hz")
    _require_positive(validated, "order")
    _require_positive(validated, "filter_order")
    _require_positive(validated, "preview_duration_s")
    _require_positive(validated, "bin_size_ms")
    _require_non_negative(validated, "smoothing_sigma_ms")
    _require_positive(validated, "max_interval_ms")
    _require_positive(validated, "max_lag_ms")
    _require_positive(validated, "window_ms")
    _require_positive(validated, "phase_min_hz")
    _require_positive(validated, "phase_max_hz")
    _require_positive(validated, "phase_step_hz")
    _require_positive(validated, "phase_bandwidth_hz")
    _require_positive(validated, "amp_min_hz")
    _require_positive(validated, "amp_max_hz")
    _require_positive(validated, "amp_step_hz")
    _require_positive(validated, "amp_bandwidth_hz")
    _require_positive(validated, "phase_bins")
    _require_positive(validated, "surrogate_runs")
    _require_positive(validated, "min_shift_s")
    _require_positive(validated, "summary_max_units")
    _require_positive(validated, "max_units")
    _require_positive(validated, "max_cycles")
    _require_positive(validated, "min_spikes_per_unit")
    _require_non_negative(validated, "cluster_seed")
    _require_positive(validated, "plot_line_width")
    _require_positive(validated, "plot_marker_size")
    _require_positive(validated, "plot_marker_halfwidth_deg")
    _require_non_negative(validated, "plot_cycle_line_alpha")
    _require_non_negative(validated, "plot_wave_overlay_alpha")

    if {"nperseg", "noverlap"}.issubset(validated):
        nperseg = int(validated["nperseg"])
        noverlap = int(validated["noverlap"])
        validated["nperseg"] = nperseg
        validated["noverlap"] = noverlap
        if noverlap >= nperseg:
            raise ValueError("Parameter `noverlap` must be smaller than `nperseg`.")

    if {"low_hz", "high_hz"}.issubset(validated):
        low_hz = float(validated["low_hz"])
        high_hz = float(validated["high_hz"])
        validated["low_hz"] = low_hz
        validated["high_hz"] = high_hz
        if low_hz >= high_hz:
            raise ValueError("Parameter `low_hz` must be smaller than `high_hz`.")

    if {"min_freq_hz", "max_freq_hz"}.issubset(validated):
        _validate_range_pair(validated, "min_freq_hz", "max_freq_hz")

    if {"phase_min_hz", "phase_max_hz"}.issubset(validated):
        phase_min_hz = float(validated["phase_min_hz"])
        phase_max_hz = float(validated["phase_max_hz"])
        validated["phase_min_hz"] = phase_min_hz
        validated["phase_max_hz"] = phase_max_hz
        if phase_min_hz >= phase_max_hz:
            raise ValueError("Parameter `phase_min_hz` must be smaller than `phase_max_hz`.")

    if {"amp_min_hz", "amp_max_hz"}.issubset(validated):
        amp_min_hz = float(validated["amp_min_hz"])
        amp_max_hz = float(validated["amp_max_hz"])
        validated["amp_min_hz"] = amp_min_hz
        validated["amp_max_hz"] = amp_max_hz
        if amp_min_hz >= amp_max_hz:
            raise ValueError("Parameter `amp_min_hz` must be smaller than `amp_max_hz`.")

    if {"y_min_db", "y_max_db"}.issubset(validated):
        _validate_range_pair(validated, "y_min_db", "y_max_db")

    if {"vmin_db", "vmax_db"}.issubset(validated):
        _validate_range_pair(validated, "vmin_db", "vmax_db")

    if bool(validated.get("plot_use_custom_x_range")):
        _validate_range_pair(validated, "plot_x_min", "plot_x_max")

    if bool(validated.get("plot_use_custom_y_range")):
        _validate_range_pair(validated, "plot_y_min", "plot_y_max")

    if bool(validated.get("plot_use_custom_color_range")):
        _validate_range_pair(validated, "plot_color_min", "plot_color_max")

    if "window_function" in validated:
        validated["window_function"] = _validate_choice(
            "window_function",
            str(validated["window_function"]),
            WINDOW_FUNCTION_CHOICES,
        )

    if "welch_average" in validated:
        validated["welch_average"] = _validate_choice(
            "welch_average",
            str(validated["welch_average"]),
            WELCH_AVERAGE_CHOICES,
        )

    if "plot_colormap" in validated:
        validated["plot_colormap"] = _validate_choice(
            "plot_colormap",
            str(validated["plot_colormap"]),
            COLORMAP_CHOICES,
        )

    if "detrend_mode" in validated:
        validated["detrend_mode"] = _validate_choice(
            "detrend_mode",
            str(validated["detrend_mode"]),
            DETREND_CHOICES,
        )

    if "spectrum_scaling" in validated:
        validated["spectrum_scaling"] = _validate_choice(
            "spectrum_scaling",
            str(validated["spectrum_scaling"]),
            SPECTRUM_SCALING_CHOICES,
        )

    if "plot_polar_zero_location" in validated:
        validated["plot_polar_zero_location"] = _validate_choice(
            "plot_polar_zero_location",
            str(validated["plot_polar_zero_location"]),
            POLAR_ZERO_LOCATION_CHOICES,
        )

    if "plot_polar_direction" in validated:
        validated["plot_polar_direction"] = _validate_choice(
            "plot_polar_direction",
            str(validated["plot_polar_direction"]),
            POLAR_DIRECTION_CHOICES,
        )

    if "unit_sort_mode" in validated:
        validated["unit_sort_mode"] = _validate_choice(
            "unit_sort_mode",
            str(validated["unit_sort_mode"]),
            POPULATION_SORT_CHOICES,
        )

    waveform_axis_keys = ("summary_x_feature", "summary_y_feature", "summary_z_feature")
    waveform_axis_values: list[str] = []
    for key in waveform_axis_keys:
        if key not in validated:
            continue
        choice = _validate_choice(key, str(validated[key]), WAVEFORM_SUMMARY_FEATURE_CHOICES)
        validated[key] = choice
        waveform_axis_values.append(choice)
    if len(set(waveform_axis_values)) != len(waveform_axis_values):
        raise ValueError(
            "Parameters `summary_x_feature`, `summary_y_feature`, and `summary_z_feature` must be distinct."
        )

    if "plot_polar_tick_step_deg" in validated:
        tick_step = int(validated["plot_polar_tick_step_deg"])
        validated["plot_polar_tick_step_deg"] = tick_step
        if tick_step <= 0 or 360 % tick_step != 0:
            raise ValueError("Parameter `plot_polar_tick_step_deg` must be a positive divisor of 360.")

    if "plot_cycle_line_alpha" in validated and float(validated["plot_cycle_line_alpha"]) > 1.0:
        raise ValueError("Parameter `plot_cycle_line_alpha` must be between 0 and 1.")

    if "plot_wave_overlay_alpha" in validated and float(validated["plot_wave_overlay_alpha"]) > 1.0:
        raise ValueError("Parameter `plot_wave_overlay_alpha` must be between 0 and 1.")

    if "alpha" in validated:
        alpha = float(validated["alpha"])
        validated["alpha"] = alpha
        if not 0.0 < alpha < 1.0:
            raise ValueError("Parameter `alpha` must be between 0 and 1.")

    if node.analysis_key == "rate_power_metrics" and {"bin_size_ms", "max_freq_hz"}.issubset(validated):
        rate_nyquist_hz = 500.0 / float(validated["bin_size_ms"])
        if float(validated["max_freq_hz"]) >= rate_nyquist_hz:
            raise ValueError(f"`max_freq_hz` must be below spike rate Nyquist frequency {rate_nyquist_hz:.2f} Hz.")

    nyquist_hz = _resolve_nyquist_hz(session, node)
    if nyquist_hz is not None:
        if "max_freq_hz" in validated:
            max_freq_hz = float(validated["max_freq_hz"])
            validated["max_freq_hz"] = max_freq_hz
            if max_freq_hz >= nyquist_hz:
                raise ValueError(f"Parameter `max_freq_hz` must be below Nyquist frequency {nyquist_hz:.2f} Hz.")
        if "high_hz" in validated:
            high_hz = float(validated["high_hz"])
            validated["high_hz"] = high_hz
            if high_hz >= nyquist_hz:
                raise ValueError(f"Parameter `high_hz` must be below Nyquist frequency {nyquist_hz:.2f} Hz.")
        if {"phase_min_hz", "phase_max_hz", "phase_bandwidth_hz"}.issubset(validated):
            phase_low_hz = float(validated["phase_min_hz"]) - float(validated["phase_bandwidth_hz"]) / 2.0
            phase_high_hz = float(validated["phase_max_hz"]) + float(validated["phase_bandwidth_hz"]) / 2.0
            if phase_low_hz <= 0.0:
                raise ValueError("Parameter `phase_min_hz` must stay above half the phase bandwidth.")
            if phase_high_hz >= nyquist_hz:
                raise ValueError(f"PAC phase band must stay below Nyquist frequency {nyquist_hz:.2f} Hz.")
        if {"amp_min_hz", "amp_max_hz", "amp_bandwidth_hz"}.issubset(validated):
            amp_low_hz = float(validated["amp_min_hz"]) - float(validated["amp_bandwidth_hz"]) / 2.0
            amp_high_hz = float(validated["amp_max_hz"]) + float(validated["amp_bandwidth_hz"]) / 2.0
            if amp_low_hz <= 0.0:
                raise ValueError("Parameter `amp_min_hz` must stay above half the amplitude bandwidth.")
            if amp_high_hz >= nyquist_hz:
                raise ValueError(f"PAC amplitude band must stay below Nyquist frequency {nyquist_hz:.2f} Hz.")

    return validated


def _require_positive(params: dict[str, Any], key: str) -> None:
    if key not in params:
        return
    value = float(params[key])
    if value <= 0:
        raise ValueError(f"Parameter `{key}` must be greater than 0.")


def _require_non_negative(params: dict[str, Any], key: str) -> None:
    if key not in params:
        return
    value = float(params[key])
    if value < 0:
        raise ValueError(f"Parameter `{key}` cannot be negative.")


def _validate_range_pair(params: dict[str, Any], minimum_key: str, maximum_key: str) -> None:
    minimum_value = float(params[minimum_key])
    maximum_value = float(params[maximum_key])
    params[minimum_key] = minimum_value
    params[maximum_key] = maximum_value
    if minimum_value >= maximum_value:
        raise ValueError(f"Parameter `{minimum_key}` must be smaller than `{maximum_key}`.")


def _validate_choice(key: str, value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        choices = ", ".join(allowed)
        raise ValueError(f"Parameter `{key}` must be one of: {choices}.")
    return value


def _resolve_nyquist_hz(session: SessionData, node: AnalysisNode) -> float | None:
    sampling_rates_hz: list[float] = []
    for ref_key in ("lfp", "lfp_a", "lfp_b"):
        variable_name = node.source_refs.get(ref_key)
        if variable_name is None:
            continue
        sampling_rates_hz.append(float(session.get_lfp_channel(variable_name).sample_rate_hz))
    if not sampling_rates_hz:
        return None
    return min(sampling_rates_hz) / 2.0
