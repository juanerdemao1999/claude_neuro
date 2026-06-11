from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from .models import (
    ContinuousData,
    LFPChannel,
    RegionMapping,
    SessionData,
    SpikeData,
    SpikeUnit,
    normalize_region_map,
    unpack_region_assignment,
)


class InMemorySessionStore:
    def __init__(self, base_session: SessionData, lfp_data: dict[str, ContinuousData], spike_data: dict[str, SpikeData]):
        self._base_session = base_session
        self._lfp_data = lfp_data
        self._spike_data = spike_data

    def load_lfp_channel(self, variable_name: str) -> ContinuousData:
        return self._lfp_data[variable_name]

    def load_spike_unit(self, variable_name: str, waveform_name: str | None = None) -> SpikeData:
        return self._spike_data[variable_name]

    def reload_session(self, manual_channel_ids: dict[str, int], region_map: RegionMapping) -> SessionData:
        normalized_region_map = normalize_region_map(region_map)
        updated_lfp = []
        for channel in self._base_session.lfp_channels:
            new_channel_id = manual_channel_ids.get(channel.variable_name, channel.channel_id)
            region, subject = unpack_region_assignment(normalized_region_map.get(new_channel_id))
            updated_lfp.append(
                replace(
                    channel,
                    channel_id=new_channel_id,
                    region=region,
                    subject=subject,
                )
            )
        updated_units = []
        for unit in self._base_session.spike_units:
            new_channel_id = manual_channel_ids.get(unit.variable_name, unit.channel_id)
            region, subject = unpack_region_assignment(normalized_region_map.get(new_channel_id))
            updated_units.append(
                replace(
                    unit,
                    channel_id=new_channel_id,
                    region=region,
                    subject=subject,
                )
            )
        return replace(
            self._base_session,
            lfp_channels=updated_lfp,
            spike_units=updated_units,
            region_map=normalized_region_map,
            manual_channel_ids=dict(manual_channel_ids),
            data_store=self,
        )


def make_synthetic_session() -> SessionData:
    sampling_rate_hz = 1000.0
    duration_s = 10.0
    time_axis = np.arange(0.0, duration_s, 1.0 / sampling_rate_hz)
    lfp_values = (
        np.sin(2 * np.pi * 8.0 * time_axis)
        + 0.2 * np.sin(2 * np.pi * 40.0 * time_axis)
        + 0.05 * np.random.default_rng(7).standard_normal(len(time_axis))
    )
    spike_times = np.arange(0.25, duration_s, 0.125)
    spike_times = spike_times + np.random.default_rng(3).normal(0.0, 0.002, size=len(spike_times))
    spike_times = spike_times[(spike_times > 0.0) & (spike_times < duration_s)]
    waveform_axis = np.linspace(-1.0, 1.0, 30)
    mean_waveform = -np.exp(-((waveform_axis + 0.2) ** 2) / 0.04) + 0.6 * np.exp(-((waveform_axis - 0.25) ** 2) / 0.08)
    waveforms = mean_waveform + 0.05 * np.random.default_rng(11).standard_normal((len(spike_times), len(waveform_axis)))

    lfp_channel = LFPChannel(
        name="LFP_CH1",
        channel_id=1,
        sample_rate_hz=sampling_rate_hz,
        duration_s=duration_s,
        variable_name="LFP_CH1",
        region="M1",
        channel_id_source="synthetic",
    )
    spike_unit = SpikeUnit(
        name="CH1_Unit1",
        channel_id=1,
        unit_index=1,
        timestamps_count=len(spike_times),
        variable_name="CH1_Unit1",
        waveform_name="CH1_Unit1_wf",
        waveform_points=waveforms.shape[1],
        waveform_sample_rate_hz=30000.0,
        region="M1",
        channel_id_source="synthetic",
    )
    session = SessionData(
        file_path=Path("synthetic.nex5"),
        metadata={
            "duration_s": duration_s,
            "timestamp_frequency_hz": 30000.0,
            "start_time_s": 0.0,
            "end_time_s": duration_s,
        },
        lfp_channels=[lfp_channel],
        spike_units=[spike_unit],
        region_map={1: "M1"},
        waveform_available=True,
    )
    store = InMemorySessionStore(
        session,
        lfp_data={
            "LFP_CH1": ContinuousData(
                name="LFP_CH1",
                sampling_rate_hz=sampling_rate_hz,
                values=lfp_values.astype(float),
                fragment_starts_s=np.asarray([0.0], dtype=float),
                fragment_lengths=np.asarray([len(lfp_values)], dtype=int),
            )
        },
        spike_data={
            "CH1_Unit1": SpikeData(
                name="CH1_Unit1",
                timestamps_s=np.asarray(spike_times, dtype=float),
                waveforms=np.asarray(waveforms, dtype=float),
                waveform_sample_rate_hz=30000.0,
            )
        },
    )
    return replace(session, data_store=store)


def make_waveform_population_session() -> SessionData:
    duration_s = 12.0
    waveform_sample_rate_hz = 30000.0
    waveform_axis = np.linspace(-1.0, 1.0, 48)
    rng = np.random.default_rng(41)

    unit_specs = [
        {"channel_id": 1, "unit_index": 1, "region": "M1", "label": "broad", "rate_hz": 2.8, "phase": 0.01},
        {"channel_id": 2, "unit_index": 1, "region": "M1", "label": "broad", "rate_hz": 3.2, "phase": 0.02},
        {"channel_id": 3, "unit_index": 1, "region": "S1", "label": "broad", "rate_hz": 4.0, "phase": 0.03},
        {"channel_id": 4, "unit_index": 1, "region": "M1", "label": "narrow", "rate_hz": 11.5, "phase": 0.00},
        {"channel_id": 5, "unit_index": 1, "region": "S1", "label": "narrow", "rate_hz": 13.0, "phase": 0.01},
        {"channel_id": 6, "unit_index": 1, "region": "S1", "label": "narrow", "rate_hz": 15.5, "phase": 0.02},
    ]

    spike_units: list[SpikeUnit] = []
    spike_data: dict[str, SpikeData] = {}
    region_map: dict[int, str] = {}

    for spec in unit_specs:
        channel_id = int(spec["channel_id"])
        unit_index = int(spec["unit_index"])
        variable_name = f"CH{channel_id}_Unit{unit_index}"
        rate_hz = float(spec["rate_hz"])
        inter_spike_s = 1.0 / rate_hz
        spike_times = np.arange(0.2 + float(spec["phase"]), duration_s - 0.2, inter_spike_s)
        spike_times = spike_times + rng.normal(0.0, 0.0015, size=len(spike_times))
        spike_times = spike_times[(spike_times > 0.0) & (spike_times < duration_s)]

        if spec["label"] == "broad":
            mean_waveform = (
                -1.1 * np.exp(-((waveform_axis + 0.18) ** 2) / 0.095)
                + 0.55 * np.exp(-((waveform_axis - 0.24) ** 2) / 0.11)
            )
            waveform_noise = 0.035
        else:
            mean_waveform = (
                -1.0 * np.exp(-((waveform_axis + 0.06) ** 2) / 0.018)
                + 0.7 * np.exp(-((waveform_axis - 0.10) ** 2) / 0.03)
            )
            waveform_noise = 0.03

        waveforms = mean_waveform + waveform_noise * rng.standard_normal((len(spike_times), len(waveform_axis)))
        spike_units.append(
            SpikeUnit(
                name=variable_name,
                channel_id=channel_id,
                unit_index=unit_index,
                timestamps_count=len(spike_times),
                variable_name=variable_name,
                waveform_name=f"{variable_name}_wf",
                waveform_points=waveforms.shape[1],
                waveform_sample_rate_hz=waveform_sample_rate_hz,
                region=str(spec["region"]),
                channel_id_source="synthetic",
            )
        )
        spike_data[variable_name] = SpikeData(
            name=variable_name,
            timestamps_s=np.asarray(spike_times, dtype=float),
            waveforms=np.asarray(waveforms, dtype=float),
            waveform_sample_rate_hz=waveform_sample_rate_hz,
        )
        region_map[channel_id] = str(spec["region"])

    session = SessionData(
        file_path=Path("synthetic_waveform_population.nex5"),
        metadata={
            "duration_s": duration_s,
            "timestamp_frequency_hz": waveform_sample_rate_hz,
            "start_time_s": 0.0,
            "end_time_s": duration_s,
        },
        lfp_channels=[],
        spike_units=spike_units,
        region_map=region_map,
        waveform_available=True,
    )
    store = InMemorySessionStore(session, lfp_data={}, spike_data=spike_data)
    return replace(session, data_store=store)
