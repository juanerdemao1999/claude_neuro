from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .defaults import (
    CONFIG_VERSION,
    default_analysis_defaults,
    default_enabled_analyses,
    default_export_defaults,
    default_input_defaults,
)
from .models import RegionMapping, normalize_region_map


@dataclass(slots=True)
class SessionProfile:
    version: int = CONFIG_VERSION
    input_defaults: dict[str, Any] = field(default_factory=default_input_defaults)
    channel_region_map: RegionMapping = field(default_factory=dict)
    analysis_defaults: dict[str, dict[str, Any]] = field(default_factory=default_analysis_defaults)
    node_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    enabled_analyses: dict[str, bool] = field(default_factory=default_enabled_analyses)
    export_defaults: dict[str, Any] = field(default_factory=default_export_defaults)

    @classmethod
    def default(cls) -> "SessionProfile":
        return cls()

    def resolved_params(
        self,
        analysis_key: str,
        node_id: str | None = None,
        runtime_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params = default_analysis_defaults().get(analysis_key, {})
        params.update(deepcopy(self.analysis_defaults.get(analysis_key, {})))
        if runtime_overrides:
            params.update(runtime_overrides)
        return params

    def set_analysis_defaults(self, analysis_key: str, params: dict[str, Any]) -> None:
        self.analysis_defaults[analysis_key] = deepcopy(params)

    def reset_analysis_defaults(self, analysis_key: str) -> dict[str, Any]:
        defaults = default_analysis_defaults()
        self.analysis_defaults[analysis_key] = deepcopy(defaults.get(analysis_key, {}))
        return deepcopy(self.analysis_defaults[analysis_key])

    def set_node_override(self, node_id: str, params: dict[str, Any]) -> None:
        self.node_overrides[node_id] = deepcopy(params)

    def clear_node_override(self, node_id: str) -> None:
        self.node_overrides.pop(node_id, None)

    def clone(self) -> "SessionProfile":
        return self.from_dict(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        normalized_region_map = normalize_region_map(self.channel_region_map)
        return {
            "version": self.version,
            "input_defaults": deepcopy(self.input_defaults),
            "channel_region_map": {str(key): deepcopy(value) for key, value in normalized_region_map.items()},
            "analysis_defaults": deepcopy(self.analysis_defaults),
            "node_overrides": deepcopy(self.node_overrides),
            "enabled_analyses": deepcopy(self.enabled_analyses),
            "export_defaults": deepcopy(self.export_defaults),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionProfile":
        profile = cls.default()
        profile.version = int(payload.get("version", CONFIG_VERSION))
        profile.input_defaults.update(deepcopy(payload.get("input_defaults", {})))
        profile.channel_region_map = normalize_region_map(payload.get("channel_region_map", {}))
        for analysis_key, params in payload.get("analysis_defaults", {}).items():
            merged = deepcopy(profile.analysis_defaults.get(analysis_key, {}))
            merged.update(deepcopy(params))
            profile.analysis_defaults[analysis_key] = merged
        profile.node_overrides = deepcopy(payload.get("node_overrides", profile.node_overrides))
        profile.enabled_analyses.update(deepcopy(payload.get("enabled_analyses", {})))
        profile.export_defaults.update(deepcopy(payload.get("export_defaults", {})))
        return profile

    def save_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load_json(cls, path: Path) -> "SessionProfile":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def default_autosave_profile_path() -> Path:
    return Path.home() / ".nex5_analyzer" / "autosave_profile.json"
