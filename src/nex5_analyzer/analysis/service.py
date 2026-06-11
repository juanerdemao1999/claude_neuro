from __future__ import annotations

import json
from typing import Any

from ..config import SessionProfile
from ..models import AnalysisNode, AnalysisResult, SessionData
from .registry import get_analysis_definition
from .runtime import AnalysisRuntime
from .validation import validate_analysis_request


class AnalysisService:
    def __init__(self) -> None:
        self._cache: dict[str, AnalysisResult] = {}
        self._shared_cache: dict[object, object] = {}

    def clone(self) -> "AnalysisService":
        cloned = AnalysisService()
        cloned._cache = dict(self._cache)
        cloned._shared_cache = dict(self._shared_cache)
        return cloned

    def merge_cache(self, other: "AnalysisService") -> None:
        self._cache.update(other._cache)
        self._shared_cache.update(other._shared_cache)

    def clear_result_cache(self) -> None:
        self._cache.clear()

    def clear_runtime_cache(self) -> None:
        self._shared_cache.clear()

    def compute(
        self,
        session: SessionData,
        node: AnalysisNode,
        profile: SessionProfile,
        runtime_overrides: dict[str, Any] | None = None,
        *,
        cache_result: bool = True,
    ) -> AnalysisResult:
        if node.kind == "placeholder":
            return AnalysisResult(
                node_id=node.node_id,
                title=node.label,
                kind="message",
                message=node.message or node.label,
            )
        if node.analysis_key is None:
            return AnalysisResult(
                node_id=node.node_id,
                title=node.label,
                kind="message",
                message="Select a leaf analysis node to render a preview.",
            )

        definition = get_analysis_definition(node.analysis_key)
        params = profile.resolved_params(node.analysis_key, node.node_id, runtime_overrides)
        params = validate_analysis_request(session, node, params)
        cache_key = json.dumps(
            {"file": str(session.file_path), "node": node.node_id, "params": params},
            sort_keys=True,
            ensure_ascii=False,
        )
        if cache_result and cache_key in self._cache:
            return self._cache[cache_key]

        result = definition.handler(AnalysisRuntime(session, shared_cache=self._shared_cache), node, params)
        self._apply_plot_overrides(result, params)
        if cache_result:
            self._cache[cache_key] = result
        return result

    def _apply_plot_overrides(self, result: AnalysisResult, params: dict[str, Any]) -> None:
        if result.kind == "composite":
            for panel in result.panels:
                self._apply_plot_overrides(panel, params)

        if result.kind == "message":
            return

        meta = dict(result.meta)
        if bool(params.get("plot_use_custom_x_range")) and result.kind != "polar":
            meta["x_range"] = (float(params["plot_x_min"]), float(params["plot_x_max"]))
        if bool(params.get("plot_use_custom_y_range")):
            meta["y_range"] = (float(params["plot_y_min"]), float(params["plot_y_max"]))
        if "plot_show_legend" in params:
            meta["show_legend"] = bool(params["plot_show_legend"])
        if "plot_line_width" in params:
            meta["line_width"] = float(params["plot_line_width"])
        if "plot_marker_size" in params:
            meta["marker_size"] = float(params["plot_marker_size"])
        if "plot_view_elev" in params:
            meta["view_elev"] = float(params["plot_view_elev"])
        if "plot_view_azim" in params:
            meta["view_azim"] = float(params["plot_view_azim"])
        if "plot_show_colorbar" in params:
            meta["show_colorbar"] = bool(params["plot_show_colorbar"])
        if "plot_colormap" in params:
            meta["colormap"] = str(params["plot_colormap"])
        if "plot_show_metrics_box" in params:
            meta["show_metrics_box"] = bool(params["plot_show_metrics_box"])
        if "plot_polar_zero_location" in params:
            meta["polar_zero_location"] = str(params["plot_polar_zero_location"])
        if "plot_polar_direction" in params:
            meta["polar_direction"] = str(params["plot_polar_direction"])
        if "plot_polar_tick_step_deg" in params:
            meta["polar_tick_step_deg"] = int(params["plot_polar_tick_step_deg"])
        if "plot_show_polar_grid" in params:
            meta["show_polar_grid"] = bool(params["plot_show_polar_grid"])
        if bool(params.get("plot_use_custom_color_range")):
            meta["vmin"] = float(params["plot_color_min"])
            meta["vmax"] = float(params["plot_color_max"])
        if "plot_marker_halfwidth_deg" in params:
            meta["marker_halfwidth_deg"] = float(params["plot_marker_halfwidth_deg"])
        if "plot_cycle_line_alpha" in params:
            meta["cycle_line_alpha"] = float(params["plot_cycle_line_alpha"])
        if "plot_wave_overlay" in params:
            meta["show_wave_overlay"] = bool(params["plot_wave_overlay"])
        if "plot_wave_overlay_alpha" in params:
            meta["wave_overlay_alpha"] = float(params["plot_wave_overlay_alpha"])
        result.meta = meta
