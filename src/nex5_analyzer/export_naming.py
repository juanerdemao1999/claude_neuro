from __future__ import annotations

import re

from .models import AnalysisNode, LFPChannel, SessionData, SpikeUnit


def slugify_export_token(value: str) -> str:
    normalized = re.sub(r"[^\w.-]+", "_", str(value).strip(), flags=re.UNICODE)
    normalized = normalized.strip("._").lower()
    return normalized


def build_analysis_output_stem(session: SessionData, node: AnalysisNode) -> str:
    scope = slugify_export_token(node.node_id.split(":", 1)[0]) or "analysis"
    analysis_key = slugify_export_token(node.analysis_key or "analysis") or "analysis"
    source_stem = _source_stem_for_node(session, node)
    return "_".join(part for part in [scope, analysis_key, source_stem] if part)


def _source_stem_for_node(session: SessionData, node: AnalysisNode) -> str:
    source_refs = node.source_refs
    if "lfp" in source_refs and "spike" in source_refs:
        unit = session.get_spike_unit(source_refs["spike"])
        channel = session.get_lfp_channel(source_refs["lfp"])
        return f"{_unit_export_slug(unit)}__{_channel_export_slug(channel)}"
    if "lfp_a" in source_refs and "lfp_b" in source_refs:
        first = session.get_lfp_channel(source_refs["lfp_a"])
        second = session.get_lfp_channel(source_refs["lfp_b"])
        return f"{_channel_export_slug(first)}__{_channel_export_slug(second)}"
    if "spike_a" in source_refs and "spike_b" in source_refs:
        first = session.get_spike_unit(source_refs["spike_a"])
        second = session.get_spike_unit(source_refs["spike_b"])
        return f"{_unit_export_slug(first)}__{_unit_export_slug(second)}"
    if "lfp" in source_refs:
        return _channel_export_slug(session.get_lfp_channel(source_refs["lfp"]))
    if "spike" in source_refs:
        return _unit_export_slug(session.get_spike_unit(source_refs["spike"]))

    node_suffix = slugify_export_token(node.node_id.split(":")[-1])
    subject_suffix = _session_subject_suffix(session)
    return "_".join(part for part in [node_suffix, subject_suffix] if part)


def _channel_export_slug(channel: LFPChannel) -> str:
    parts: list[str] = []
    if channel.subject:
        parts.append(slugify_export_token(channel.subject))
        if channel.region:
            parts.append(slugify_export_token(channel.region))
    parts.append(channel.slug)
    return "_".join(part for part in parts if part)


def _unit_export_slug(unit: SpikeUnit) -> str:
    parts: list[str] = []
    if unit.subject:
        parts.append(slugify_export_token(unit.subject))
        if unit.region:
            parts.append(slugify_export_token(unit.region))
    parts.append(unit.slug)
    return "_".join(part for part in parts if part)


def _session_subject_suffix(session: SessionData) -> str:
    tokens = [slugify_export_token(subject) for subject in session.subject_names if subject]
    tokens = [token for token in tokens if token]
    return "_".join(tokens[:4])
