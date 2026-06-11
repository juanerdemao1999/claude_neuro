from __future__ import annotations

import math
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from nex5file.reader import Reader

from ..models import (
    ContinuousData,
    LFPChannel,
    RegionMapping,
    SessionData,
    SpikeData,
    SpikeUnit,
    normalize_region_map,
    unpack_region_assignment,
)

CHANNEL_PATTERNS = [
    re.compile(r"CH[_\s-]?(?P<channel>\d+)", re.IGNORECASE),
    re.compile(r"LFP[_\s-]?(?P<channel>\d+)", re.IGNORECASE),
    re.compile(r"channel[_\s-]?(?P<channel>\d+)", re.IGNORECASE),
]
UNIT_PATTERN = re.compile(r"Unit[_\s-]?(?P<unit>\d+)", re.IGNORECASE)


def extract_channel_id(name: str, header_wire: int | None = None) -> int | None:
    if header_wire not in (None, 0):
        return int(header_wire)
    for pattern in CHANNEL_PATTERNS:
        match = pattern.search(name)
        if match:
            return int(match.group("channel"))
    return None


def extract_unit_index(name: str) -> int | None:
    match = UNIT_PATTERN.search(name)
    if match:
        return int(match.group("unit"))
    return None


def infer_preferred_lfp_sampling_rate(variables: list[Any]) -> float | None:
    positive_rates = [
        float(getattr(variable.header, "SamplingRate", 0.0))
        for variable in variables
        if float(getattr(variable.header, "SamplingRate", 0.0)) > 0
    ]
    if positive_rates:
        return min(positive_rates)

    rates = [float(getattr(variable.header, "SamplingRate", 0.0)) for variable in variables]
    if rates:
        return min(rates)
    return None


def is_preferred_lfp_sampling_rate(sample_rate_hz: float, preferred_rate_hz: float | None) -> bool:
    if preferred_rate_hz is None:
        return True
    return math.isclose(float(sample_rate_hz), float(preferred_rate_hz), rel_tol=1e-6, abs_tol=1e-6)


def build_sequential_channel_map(raw_channel_ids: list[int]) -> dict[int, int]:
    ordered_ids = sorted({int(channel_id) for channel_id in raw_channel_ids})
    return {channel_id: index for index, channel_id in enumerate(ordered_ids, start=1)}


class Nex5DataStore:
    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self._reader = Reader()
        self._spike_cache: dict[str, SpikeData] = {}
        self._lfp_cache: dict[str, ContinuousData] = {}

    def clear_cache(self) -> None:
        self._spike_cache.clear()
        self._lfp_cache.clear()

    def load_spike_unit(self, variable_name: str, waveform_name: str | None = None) -> SpikeData:
        cache_key = waveform_name or variable_name
        if cache_key in self._spike_cache:
            return self._spike_cache[cache_key]

        names = [variable_name]
        if waveform_name:
            names.append(waveform_name)
        data = self._reader.ReadNex5FileVariables(str(self.file_path), names)
        spike_variable = next(variable for variable in data.variables if getattr(variable.header, "Name", "") == variable_name)
        waveform_variable = None
        if waveform_name:
            waveform_variable = next(
                (variable for variable in data.variables if getattr(variable.header, "Name", "") == waveform_name),
                None,
            )

        result = SpikeData(
            name=variable_name,
            timestamps_s=np.asarray(getattr(spike_variable, "timestamps", getattr(spike_variable, "Timestamps")), dtype=float),
            waveforms=(
                np.asarray(getattr(waveform_variable, "waveform_values", getattr(waveform_variable, "WaveformValues")), dtype=float)
                if waveform_variable is not None
                else None
            ),
            waveform_sample_rate_hz=(
                float(getattr(waveform_variable.header, "SamplingRate", 0.0)) if waveform_variable is not None else None
            ),
        )
        self._spike_cache[cache_key] = result
        return result

    def load_lfp_channel(self, variable_name: str) -> ContinuousData:
        if variable_name in self._lfp_cache:
            return self._lfp_cache[variable_name]

        data = self._reader.ReadNex5FileVariables(str(self.file_path), [variable_name])
        variable = data.variables[0]
        values = np.asarray(
            getattr(variable, "continuous_values", getattr(variable, "ContinuousValues", [])),
            dtype=float,
        )
        fragment_starts = np.asarray(
            getattr(variable, "fragment_timestamps", getattr(variable, "FragmentTimestamps", [])),
            dtype=float,
        )
        fragment_lengths = np.asarray(
            getattr(variable, "fragment_counts", getattr(variable, "FragmentCounts", [])),
            dtype=int,
        )
        if fragment_lengths.size == 0 and values.size:
            fragment_starts = np.asarray([0.0], dtype=float)
            fragment_lengths = np.asarray([values.size], dtype=int)
        result = ContinuousData(
            name=variable_name,
            sampling_rate_hz=float(getattr(variable.header, "SamplingRate", 0.0)),
            values=values,
            fragment_starts_s=fragment_starts,
            fragment_lengths=fragment_lengths,
        )
        self._lfp_cache[variable_name] = result
        return result

    def reload_session(
        self,
        manual_channel_ids: dict[str, int] | None = None,
        region_map: RegionMapping | None = None,
    ) -> SessionData:
        return Nex5SessionLoader().inspect(
            self.file_path,
            manual_channel_ids=manual_channel_ids or {},
            region_map=region_map or {},
            data_store=self,
        )


class Nex5SessionLoader:
    def inspect(
        self,
        file_path: str | Path,
        manual_channel_ids: dict[str, int] | None = None,
        region_map: RegionMapping | None = None,
        data_store: Nex5DataStore | None = None,
    ) -> SessionData:
        file_path = Path(file_path)
        manual_channel_ids = dict(manual_channel_ids or {})
        region_map = normalize_region_map(region_map or {})
        data_store = data_store or Nex5DataStore(file_path)

        file_data = Reader().ReadNex5HeadersOnly(str(file_path))
        continuous_variables = [
            variable for variable in file_data.variables if type(variable).__name__ == "ContinuousVariable"
        ]
        preferred_lfp_rate_hz = infer_preferred_lfp_sampling_rate(continuous_variables)

        pending_lfp_channels: list[dict[str, Any]] = []
        pending_spike_units: list[dict[str, Any]] = []

        for variable in file_data.variables:
            header = variable.header
            name = getattr(header, "Name", type(variable).__name__)
            type_name = type(variable).__name__
            raw_channel_id = extract_channel_id(name, header_wire=getattr(header, "Wire", None))
            raw_channel_id_source = "header" if getattr(header, "Wire", None) not in (None, 0) else ("name" if raw_channel_id is not None else "unknown")

            if type_name == "ContinuousVariable":
                sample_rate_hz = float(getattr(header, "SamplingRate", 0.0))
                if not is_preferred_lfp_sampling_rate(sample_rate_hz, preferred_lfp_rate_hz):
                    continue
                pending_lfp_channels.append(
                    {
                        "name": name,
                        "sample_rate_hz": sample_rate_hz,
                        "raw_channel_id": raw_channel_id,
                        "channel_id_source": raw_channel_id_source,
                    }
                )
            elif type_name == "NeuronVariable":
                pending_spike_units.append(
                    {
                        "name": name,
                        "raw_channel_id": raw_channel_id,
                        "channel_id_source": raw_channel_id_source,
                        "unit_index": extract_unit_index(name),
                        "timestamps_count": int(getattr(header, "Count", getattr(variable, "count", 0))),
                        "waveform_name": None,
                        "waveform_points": 0,
                        "waveform_sample_rate_hz": None,
                    }
                )
            elif type_name == "WaveformVariable":
                for unit in pending_spike_units:
                    if name.startswith(unit["name"]):
                        unit["waveform_name"] = name
                        unit["waveform_points"] = int(getattr(header, "NPointsWave", 0))
                        unit["waveform_sample_rate_hz"] = float(getattr(header, "SamplingRate", 0.0))
                        break

        raw_channel_ids = [
            item["raw_channel_id"]
            for item in pending_lfp_channels + pending_spike_units
            if item["raw_channel_id"] is not None
        ]
        raw_to_sequential = build_sequential_channel_map(raw_channel_ids)

        lfp_channels = [
            LFPChannel(
                name=item["name"],
                channel_id=_resolve_mapped_channel_id(item["name"], item["raw_channel_id"], manual_channel_ids, raw_to_sequential),
                sample_rate_hz=item["sample_rate_hz"],
                duration_s=float(file_data.GetDocEndTime() - file_data.GetDocStartTime()),
                variable_name=item["name"],
                region=_resolved_region_value(
                    _resolve_mapped_channel_id(item["name"], item["raw_channel_id"], manual_channel_ids, raw_to_sequential),
                    region_map,
                )[0],
                subject=_resolved_region_value(
                    _resolve_mapped_channel_id(item["name"], item["raw_channel_id"], manual_channel_ids, raw_to_sequential),
                    region_map,
                )[1],
                channel_id_source=_resolve_channel_id_source(
                    item["name"],
                    item["raw_channel_id"],
                    manual_channel_ids,
                    item["channel_id_source"],
                ),
                raw_channel_id=item["raw_channel_id"],
            )
            for item in pending_lfp_channels
        ]
        spike_units = [
            SpikeUnit(
                name=item["name"],
                channel_id=_resolve_mapped_channel_id(item["name"], item["raw_channel_id"], manual_channel_ids, raw_to_sequential),
                unit_index=item["unit_index"],
                timestamps_count=item["timestamps_count"],
                variable_name=item["name"],
                waveform_name=item["waveform_name"],
                waveform_points=item["waveform_points"],
                waveform_sample_rate_hz=item["waveform_sample_rate_hz"],
                region=_resolved_region_value(
                    _resolve_mapped_channel_id(item["name"], item["raw_channel_id"], manual_channel_ids, raw_to_sequential),
                    region_map,
                )[0],
                subject=_resolved_region_value(
                    _resolve_mapped_channel_id(item["name"], item["raw_channel_id"], manual_channel_ids, raw_to_sequential),
                    region_map,
                )[1],
                channel_id_source=_resolve_channel_id_source(
                    item["name"],
                    item["raw_channel_id"],
                    manual_channel_ids,
                    item["channel_id_source"],
                ),
                raw_channel_id=item["raw_channel_id"],
            )
            for item in pending_spike_units
        ]

        return SessionData(
            file_path=file_path,
            metadata={
                "start_time_s": float(file_data.GetDocStartTime()),
                "end_time_s": float(file_data.GetDocEndTime()),
                "duration_s": float(file_data.GetDocEndTime() - file_data.GetDocStartTime()),
                "timestamp_frequency_hz": float(file_data.GetTimestampFrequency()),
                "variable_count": len(file_data.variables),
            },
            lfp_channels=sorted(lfp_channels, key=lambda item: (item.channel_id is None, item.channel_id or 10**9, item.name)),
            spike_units=sorted(
                spike_units,
                key=lambda item: (item.channel_id is None, item.channel_id or 10**9, item.unit_index or 10**9, item.name),
            ),
            waveform_available=any(unit.waveform_name for unit in spike_units),
            region_map=region_map,
            manual_channel_ids=manual_channel_ids,
            data_store=data_store,
        )


def _resolved_region_value(channel_id: int | None, region_map: RegionMapping) -> tuple[str | None, str | None]:
    return unpack_region_assignment(region_map.get(channel_id))


def _resolve_mapped_channel_id(
    variable_name: str,
    raw_channel_id: int | None,
    manual_channel_ids: dict[str, int],
    raw_to_sequential: dict[int, int],
) -> int | None:
    if variable_name in manual_channel_ids:
        return int(manual_channel_ids[variable_name])
    if raw_channel_id is None:
        return None
    return raw_to_sequential.get(int(raw_channel_id))


def _resolve_channel_id_source(
    variable_name: str,
    raw_channel_id: int | None,
    manual_channel_ids: dict[str, int],
    detected_source: str,
) -> str:
    if variable_name in manual_channel_ids:
        return "manual"
    if raw_channel_id is not None:
        return f"sequential_{detected_source}"
    return "unknown"
