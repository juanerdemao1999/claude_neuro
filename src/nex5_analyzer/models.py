from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd


RegionMappingValue = str | dict[str, str]
RegionMapping = dict[int, RegionMappingValue]


@dataclass(frozen=True, slots=True)
class RegionAssignment:
    region: str
    subject: str | None = None

    @property
    def label(self) -> str:
        return format_region_scope(self.region, self.subject)

    @property
    def key(self) -> tuple[str, str]:
        return (self.subject or "", self.region)


def normalize_region_assignment(value: Any) -> RegionAssignment | None:
    if value is None:
        return None

    region = ""
    subject = ""
    if isinstance(value, RegionAssignment):
        region = str(value.region).strip()
        subject = str(value.subject or "").strip()
    elif isinstance(value, str):
        region = value.strip()
    elif isinstance(value, Mapping):
        region = str(value.get("region", "")).strip()
        subject = str(value.get("subject", value.get("mouse", "")) or "").strip()
    else:
        region = str(value).strip()

    if not region:
        return None
    return RegionAssignment(region=region, subject=subject or None)


def serialize_region_assignment(value: Any) -> RegionMappingValue | None:
    assignment = normalize_region_assignment(value)
    if assignment is None:
        return None
    if assignment.subject:
        return {"subject": assignment.subject, "region": assignment.region}
    return assignment.region


def normalize_region_map(region_map: Mapping[int | str, Any] | None) -> RegionMapping:
    normalized: RegionMapping = {}
    if not region_map:
        return normalized

    for key, value in region_map.items():
        try:
            channel_id = int(key)
        except (TypeError, ValueError):
            continue
        serialized = serialize_region_assignment(value)
        if serialized is not None:
            normalized[channel_id] = serialized
    return normalized


def unpack_region_assignment(value: Any) -> tuple[str | None, str | None]:
    assignment = normalize_region_assignment(value)
    if assignment is None:
        return None, None
    return assignment.region, assignment.subject


def region_scope_key(region: str | None, subject: str | None = None) -> tuple[str, str] | None:
    region_text = str(region or "").strip()
    if not region_text:
        return None
    return (str(subject or "").strip(), region_text)


def format_region_scope(
    region: str | None,
    subject: str | None = None,
    *,
    unmapped_label: str = "Unmapped",
) -> str:
    region_text = str(region or "").strip()
    if not region_text:
        return unmapped_label
    subject_text = str(subject or "").strip()
    if subject_text:
        return f"{subject_text} / {region_text}"
    return region_text


@dataclass(slots=True)
class LFPChannel:
    name: str
    channel_id: int | None
    sample_rate_hz: float
    duration_s: float
    variable_name: str
    region: str | None = None
    subject: str | None = None
    channel_id_source: str = "unknown"
    raw_channel_id: int | None = None

    @property
    def slug(self) -> str:
        if self.channel_id is not None:
            return f"ch{self.channel_id:02d}"
        return sanitize_slug(self.name)

    @property
    def region_scope(self) -> tuple[str, str] | None:
        return region_scope_key(self.region, self.subject)

    @property
    def region_label(self) -> str:
        return format_region_scope(self.region, self.subject)

    @property
    def display_name(self) -> str:
        if self.channel_id is not None:
            return f"{self.slug}({self.region_label})"
        return f"{self.name}({self.region_label})"


@dataclass(slots=True)
class SpikeUnit:
    name: str
    channel_id: int | None
    unit_index: int | None
    timestamps_count: int
    variable_name: str
    waveform_name: str | None = None
    waveform_points: int = 0
    waveform_sample_rate_hz: float | None = None
    region: str | None = None
    subject: str | None = None
    channel_id_source: str = "unknown"
    raw_channel_id: int | None = None

    @property
    def slug(self) -> str:
        channel_part = f"ch{self.channel_id:02d}" if self.channel_id is not None else sanitize_slug(self.name)
        unit_part = f"u{self.unit_index:02d}" if self.unit_index is not None else "u00"
        return f"unit_{channel_part}_{unit_part}"

    @property
    def region_scope(self) -> tuple[str, str] | None:
        return region_scope_key(self.region, self.subject)

    @property
    def region_label(self) -> str:
        return format_region_scope(self.region, self.subject)

    @property
    def display_name(self) -> str:
        if self.channel_id is not None and self.unit_index is not None:
            return f"unit ch{self.channel_id:02d}_u{self.unit_index:02d}({self.region_label})"
        return f"{self.name}({self.region_label})"


@dataclass(slots=True)
class ContinuousData:
    name: str
    sampling_rate_hz: float
    values: np.ndarray
    fragment_starts_s: np.ndarray
    fragment_lengths: np.ndarray

    def fragments(self) -> list[tuple[np.ndarray, np.ndarray]]:
        if len(self.fragment_lengths) == 0:
            times = np.arange(len(self.values), dtype=float) / self.sampling_rate_hz
            return [(times, self.values)]

        fragments: list[tuple[np.ndarray, np.ndarray]] = []
        cursor = 0
        for start_s, length in zip(self.fragment_starts_s, self.fragment_lengths, strict=False):
            fragment_values = self.values[cursor : cursor + int(length)]
            cursor += int(length)
            fragment_times = start_s + np.arange(int(length), dtype=float) / self.sampling_rate_hz
            fragments.append((fragment_times, fragment_values))
        return fragments

    def preferred_fragment(self) -> tuple[np.ndarray, np.ndarray]:
        fragments = self.fragments()
        if not fragments:
            return np.asarray([], dtype=float), np.asarray([], dtype=float)
        return max(fragments, key=lambda item: len(item[0]))


@dataclass(slots=True)
class SpikeData:
    name: str
    timestamps_s: np.ndarray
    waveforms: np.ndarray | None = None
    waveform_sample_rate_hz: float | None = None


@dataclass(slots=True)
class PlotSeries:
    label: str
    x: np.ndarray
    y: np.ndarray


@dataclass(slots=True)
class AnalysisResult:
    node_id: str
    title: str
    kind: str
    x_label: str = ""
    y_label: str = ""
    color_label: str = ""
    series: list[PlotSeries] = field(default_factory=list)
    image: np.ndarray | None = None
    image_x: np.ndarray | None = None
    image_y: np.ndarray | None = None
    message: str | None = None
    export_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    meta: dict[str, Any] = field(default_factory=dict)
    panels: list["AnalysisResult"] = field(default_factory=list)
    z_label: str = ""


@dataclass(slots=True)
class AnalysisNode:
    node_id: str
    label: str
    kind: str
    analysis_key: str | None = None
    source_refs: dict[str, str] = field(default_factory=dict)
    message: str | None = None
    children: list["AnalysisNode"] = field(default_factory=list)

    def add_child(self, child: "AnalysisNode") -> None:
        self.children.append(child)

    def find_node(self, node_id: str) -> "AnalysisNode":
        if self.node_id == node_id:
            return self
        for child in self.children:
            try:
                return child.find_node(node_id)
            except KeyError:
                continue
        raise KeyError(node_id)


@dataclass(slots=True)
class SessionData:
    file_path: Path
    metadata: dict[str, Any]
    lfp_channels: list[LFPChannel]
    spike_units: list[SpikeUnit]
    region_map: RegionMapping = field(default_factory=dict)
    waveform_available: bool = False
    manual_channel_ids: dict[str, int] = field(default_factory=dict)
    data_store: Any = None

    def with_region_map(self, region_map: Mapping[int | str, Any]) -> "SessionData":
        normalized_map = normalize_region_map(region_map)
        updated_lfp = []
        for channel in self.lfp_channels:
            region, subject = unpack_region_assignment(normalized_map.get(channel.channel_id))
            updated_lfp.append(replace(channel, region=region, subject=subject))
        updated_units = []
        for unit in self.spike_units:
            region, subject = unpack_region_assignment(normalized_map.get(unit.channel_id))
            updated_units.append(replace(unit, region=region, subject=subject))
        return replace(self, lfp_channels=updated_lfp, spike_units=updated_units, region_map=normalized_map)

    @property
    def file_name(self) -> str:
        return self.file_path.name

    @property
    def channel_ids(self) -> list[int]:
        ids = {channel.channel_id for channel in self.lfp_channels if channel.channel_id is not None}
        ids.update(unit.channel_id for unit in self.spike_units if unit.channel_id is not None)
        return sorted(int(value) for value in ids)

    def get_lfp_channel(self, variable_name: str) -> LFPChannel:
        for channel in self.lfp_channels:
            if channel.variable_name == variable_name:
                return channel
        raise KeyError(variable_name)

    def get_spike_unit(self, variable_name: str) -> SpikeUnit:
        for unit in self.spike_units:
            if unit.variable_name == variable_name:
                return unit
        raise KeyError(variable_name)

    @property
    def subject_names(self) -> list[str]:
        names = {
            str(subject).strip()
            for subject in [
                *(channel.subject for channel in self.lfp_channels),
                *(unit.subject for unit in self.spike_units),
            ]
            if str(subject or "").strip()
        }
        return sorted(names)


def sanitize_slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_")
