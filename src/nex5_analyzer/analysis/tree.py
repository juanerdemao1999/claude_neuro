from __future__ import annotations

from itertools import combinations

from ..config import SessionProfile
from ..models import AnalysisNode, SessionData
from .registry import AnalysisDefinition, iter_analysis_definitions


class AnalysisTreeBuilder:
    def build(self, session: SessionData, profile: SessionProfile) -> AnalysisNode:
        root = AnalysisNode("root", "Analysis", "category")
        root.add_child(self._build_lfp(session, profile))
        root.add_child(self._build_spike(session, profile))
        root.add_child(self._build_lfp_lfp(session, profile))
        root.add_child(self._build_spike_lfp(session, profile))
        return root

    def _build_lfp(self, session: SessionData, profile: SessionProfile) -> AnalysisNode:
        category = AnalysisNode("category:lfp", "LFP", "category")
        if not session.lfp_channels:
            category.add_child(
                AnalysisNode(
                    "placeholder:lfp:none",
                    "No LFP channels available in this session.",
                    "placeholder",
                    message="The loaded NEX5 file does not contain continuous LFP channels.",
                )
            )
            return category

        for definition in iter_analysis_definitions("lfp"):
            if not profile.enabled_analyses.get(definition.key, True):
                continue
            subcategory = AnalysisNode(f"subcategory:lfp:{definition.key}", definition.label, "category")
            for channel in session.lfp_channels:
                subcategory.add_child(
                    AnalysisNode(
                        node_id=f"lfp:{definition.key}:{channel.slug}",
                        label=channel.display_name,
                        kind="leaf",
                        analysis_key=definition.key,
                        source_refs={"lfp": channel.variable_name},
                    )
                )
            category.add_child(subcategory)
        return category

    def _build_spike(self, session: SessionData, profile: SessionProfile) -> AnalysisNode:
        category = AnalysisNode("category:spike", "Spike", "category")
        if not session.spike_units:
            category.add_child(
                AnalysisNode(
                    "placeholder:spike:none",
                    "No spike units available in this session.",
                    "placeholder",
                    message="The loaded NEX5 file does not contain sorted spike units.",
                )
            )
            return category

        for definition in iter_analysis_definitions("spike"):
            if not profile.enabled_analyses.get(definition.key, True):
                continue
            category.add_child(self._build_spike_definition_subtree(session, definition))
        return category

    def _build_lfp_lfp(self, session: SessionData, profile: SessionProfile) -> AnalysisNode:
        category = AnalysisNode("category:lfp_lfp", "LFP-LFP", "category")
        if len(session.lfp_channels) < 2:
            category.add_child(
                AnalysisNode(
                    "placeholder:lfp_lfp:none",
                    "Need at least two LFP channels.",
                    "placeholder",
                    message="Pairwise LFP coherence needs two or more continuous channels.",
                )
            )
            return category

        for definition in iter_analysis_definitions("lfp_lfp"):
            if not profile.enabled_analyses.get(definition.key, True):
                continue
            if definition.build_mode == "session_single":
                category.add_child(
                    AnalysisNode(
                        "lfp_lfp:region_summary:matrix",
                        definition.label,
                        "leaf",
                        analysis_key=definition.key,
                    )
                )
                continue

            subcategory = AnalysisNode(f"subcategory:lfp_lfp:{definition.key}", definition.label, "category")
            for first, second in combinations(session.lfp_channels, 2):
                subcategory.add_child(
                    AnalysisNode(
                        f"lfp_lfp:{definition.key}:{first.slug}__{second.slug}",
                        f"{first.display_name} vs {second.display_name}",
                        "leaf",
                        analysis_key=definition.key,
                        source_refs={"lfp_a": first.variable_name, "lfp_b": second.variable_name},
                    )
                )
            category.add_child(subcategory)
        return category

    def _build_spike_lfp(self, session: SessionData, profile: SessionProfile) -> AnalysisNode:
        category = AnalysisNode("category:spike_lfp", "Spike-LFP", "category")
        if not session.spike_units or not session.lfp_channels:
            category.add_child(
                AnalysisNode(
                    "placeholder:spike_lfp:none",
                    "Need both spike units and LFP channels.",
                    "placeholder",
                    message="Spike-LFP analyses only appear when the session contains both spikes and LFP.",
                )
            )
            return category

        for definition in iter_analysis_definitions("spike_lfp"):
            if not profile.enabled_analyses.get(definition.key, True):
                continue
            if definition.build_mode == "spike_lfp_lfp_each":
                subcategory = AnalysisNode(f"subcategory:spike_lfp:{definition.key}", definition.label, "category")
                for channel in session.lfp_channels:
                    subcategory.add_child(
                        AnalysisNode(
                            f"spike_lfp:{definition.key}:{channel.slug}",
                            channel.display_name,
                            "leaf",
                            analysis_key=definition.key,
                            source_refs={"lfp": channel.variable_name},
                        )
                    )
                category.add_child(subcategory)
                continue
            subcategory = AnalysisNode(f"subcategory:spike_lfp:{definition.key}", definition.label, "category")
            for unit in session.spike_units:
                for channel in session.lfp_channels:
                    subcategory.add_child(
                        AnalysisNode(
                            f"spike_lfp:{definition.key}:{unit.slug}__{channel.slug}",
                            f"{unit.display_name} vs {channel.display_name}",
                            "leaf",
                            analysis_key=definition.key,
                            source_refs={"spike": unit.variable_name, "lfp": channel.variable_name},
                        )
                    )
            category.add_child(subcategory)
        return category

    def _build_spike_definition_subtree(self, session: SessionData, definition: AnalysisDefinition) -> AnalysisNode:
        subcategory = AnalysisNode(f"subcategory:spike:{definition.key}", definition.label, "category")
        if definition.build_mode == "spike_summary_and_each":
            subcategory.add_child(
                AnalysisNode(
                    f"spike:{definition.key}:summary",
                    "All units summary",
                    "leaf",
                    analysis_key=definition.key,
                )
            )
            for unit in session.spike_units:
                subcategory.add_child(
                    AnalysisNode(
                        f"spike:{definition.key}:{unit.slug}",
                        unit.display_name,
                        "leaf",
                        analysis_key=definition.key,
                        source_refs={"spike": unit.variable_name},
                    )
                )
            return subcategory

        if definition.build_mode == "spike_pair":
            if len(session.spike_units) < 2:
                subcategory.add_child(
                    AnalysisNode(
                        "placeholder:spike:cross_correlation",
                        "Need at least two units for cross-correlation.",
                        "placeholder",
                        message="Cross-correlation requires two or more spike units.",
                    )
                )
                return subcategory
            for first, second in combinations(session.spike_units, 2):
                subcategory.add_child(
                    AnalysisNode(
                        f"spike:{definition.key}:{first.slug}__{second.slug}",
                        f"{first.display_name} vs {second.display_name}",
                        "leaf",
                        analysis_key=definition.key,
                        source_refs={"spike_a": first.variable_name, "spike_b": second.variable_name},
                    )
                )
            return subcategory

        for unit in session.spike_units:
            subcategory.add_child(
                AnalysisNode(
                    f"spike:{definition.key}:{unit.slug}",
                    unit.display_name,
                    "leaf",
                    analysis_key=definition.key,
                    source_refs={"spike": unit.variable_name},
                )
            )
        return subcategory
