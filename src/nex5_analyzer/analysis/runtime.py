from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..models import ContinuousData, SessionData, SpikeData


@dataclass(slots=True)
class AnalysisRuntime:
    session: SessionData
    shared_cache: dict[object, Any] = field(default_factory=dict)

    def load_channel(self, variable_name: str) -> ContinuousData:
        return self.session.data_store.load_lfp_channel(variable_name)

    def load_channel_fragment(self, variable_name: str) -> tuple[np.ndarray, np.ndarray]:
        cache_key = ("channel_fragment", variable_name)
        return self.cache_get_or_create(cache_key, lambda: self.load_channel(variable_name).preferred_fragment())

    def load_spike(self, variable_name: str) -> SpikeData:
        unit = self.session.get_spike_unit(variable_name)
        return self.session.data_store.load_spike_unit(unit.variable_name, unit.waveform_name)

    def cache_get_or_create(self, cache_key: object, factory: Callable[[], Any]) -> Any:
        session_cache_key = (str(self.session.file_path), cache_key)
        if session_cache_key not in self.shared_cache:
            self.shared_cache[session_cache_key] = factory()
        return self.shared_cache[session_cache_key]
