from __future__ import annotations

from copy import deepcopy

from .analysis.registry import ParameterSpec, analysis_defaults_by_key, enabled_analyses_by_key, parameter_specs_by_key


CONFIG_VERSION = 1

INPUT_DEFAULTS = {
    "manual_channel_ids": {},
    "batch_input_dir": "",
    "batch_output_dir": "",
}

ANALYSIS_DEFAULTS = analysis_defaults_by_key()

ENABLED_ANALYSES = enabled_analyses_by_key()

EXPORT_DEFAULTS = {
    "figure_formats": ["png", "svg"],
    "data_format": "csv",
}

PARAMETER_SPECS: dict[str, list[ParameterSpec]] = parameter_specs_by_key()


def default_analysis_defaults() -> dict:
    return deepcopy(ANALYSIS_DEFAULTS)


def default_enabled_analyses() -> dict:
    return deepcopy(ENABLED_ANALYSES)


def default_export_defaults() -> dict:
    return deepcopy(EXPORT_DEFAULTS)


def default_input_defaults() -> dict:
    return deepcopy(INPUT_DEFAULTS)
