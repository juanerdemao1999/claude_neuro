"""NEX5 Spike/LFP desktop analyzer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "AnalysisNode",
    "LFPChannel",
    "SessionData",
    "SessionProfile",
    "SpikeUnit",
]

if TYPE_CHECKING:
    from .config import SessionProfile
    from .models import AnalysisNode, LFPChannel, SessionData, SpikeUnit


def __getattr__(name: str) -> Any:
    if name == "SessionProfile":
        from .config import SessionProfile

        return SessionProfile
    if name in {"AnalysisNode", "LFPChannel", "SessionData", "SpikeUnit"}:
        from .models import AnalysisNode, LFPChannel, SessionData, SpikeUnit

        return {
            "AnalysisNode": AnalysisNode,
            "LFPChannel": LFPChannel,
            "SessionData": SessionData,
            "SpikeUnit": SpikeUnit,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
