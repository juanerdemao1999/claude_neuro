from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import quantities as pq
from elephant.conversion import BinnedSpikeTrain
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

import nex5_analyzer.analysis.lfp as lfp_module
import nex5_analyzer.analysis.lfp_lfp as lfp_lfp_module
import nex5_analyzer.analysis.spike as spike_module
import nex5_analyzer.analysis.spike_lfp as spike_lfp_module
from nex5_analyzer.analysis.service import AnalysisService
from nex5_analyzer.analysis.tree import AnalysisTreeBuilder
from nex5_analyzer.config import SessionProfile
from nex5_analyzer.models import AnalysisResult, ContinuousData, LFPChannel, PlotSeries, SessionData, SpikeData, SpikeUnit
from nex5_analyzer.plotting import create_publication_figure, render_publication_axes
from nex5_analyzer.testing import InMemorySessionStore, make_synthetic_session, make_waveform_population_session


def _make_pac_synthetic_session() -> SessionData:
    sampling_rate_hz = 1000.0
    duration_s = 12.0
    time_axis = np.arange(0.0, duration_s, 1.0 / sampling_rate_hz)
    phase_frequency_hz = 6.0
    amplitude_frequency_hz = 80.0
    rng = np.random.default_rng(21)

    slow_phase = np.sin(2 * np.pi * phase_frequency_hz * time_axis)
    amplitude_envelope = 1.0 + 0.85 * np.sin(2 * np.pi * phase_frequency_hz * time_axis - np.pi / 6.0)
    values = (
        0.8 * slow_phase
        + 0.35 * np.sin(2 * np.pi * 18.0 * time_axis)
        + amplitude_envelope * np.sin(2 * np.pi * amplitude_frequency_hz * time_axis)
        + 0.05 * rng.standard_normal(len(time_axis))
    )

    channel = LFPChannel(
        name="PAC_LFP",
        channel_id=1,
        sample_rate_hz=sampling_rate_hz,
        duration_s=duration_s,
        variable_name="PAC_LFP",
        region="M1",
        channel_id_source="synthetic",
    )
    session = SessionData(
        file_path=Path("synthetic_pac.nex5"),
        metadata={
            "duration_s": duration_s,
            "timestamp_frequency_hz": 30000.0,
            "start_time_s": 0.0,
            "end_time_s": duration_s,
        },
        lfp_channels=[channel],
        spike_units=[],
        region_map={1: "M1"},
        waveform_available=False,
    )
    store = InMemorySessionStore(
        session,
        lfp_data={
            "PAC_LFP": ContinuousData(
                name="PAC_LFP",
                sampling_rate_hz=sampling_rate_hz,
                values=values.astype(float),
                fragment_starts_s=np.asarray([0.0], dtype=float),
                fragment_lengths=np.asarray([len(values)], dtype=int),
            )
        },
        spike_data={},
    )
    return replace(session, data_store=store)


def _draw_renderer(figure: Figure):
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    return canvas.get_renderer()


def _metrics_artist(axis):
    candidates = [axis.title]
    if hasattr(axis, "_left_title"):
        candidates.append(axis._left_title)
    if hasattr(axis, "_right_title"):
        candidates.append(axis._right_title)
    candidates.extend(axis.texts)
    return next(artist for artist in candidates if artist.get_gid() == "analysis-metrics-box")


def _make_population_coding_session() -> SessionData:
    sampling_rate_hz = 1000.0
    duration_s = 8.0
    theta_frequency_hz = 6.0
    time_axis = np.arange(0.0, duration_s, 1.0 / sampling_rate_hz)
    lfp_values = np.sin(2 * np.pi * theta_frequency_hz * time_axis)

    phase_offsets_deg = [300.0, 220.0, 140.0]
    region_map = {1: "M1"}
    lfp_channel = LFPChannel(
        name="THETA_LFP",
        channel_id=1,
        sample_rate_hz=sampling_rate_hz,
        duration_s=duration_s,
        variable_name="THETA_LFP",
        region="M1",
        channel_id_source="synthetic",
    )

    spike_units: list[SpikeUnit] = []
    spike_data: dict[str, SpikeData] = {}
    theta_period_s = 1.0 / theta_frequency_hz
    cycle_starts = np.arange(0.0, duration_s, theta_period_s)

    for index, phase_deg in enumerate(phase_offsets_deg, start=1):
        spike_times = cycle_starts + (phase_deg / 360.0) * theta_period_s
        spike_times = spike_times[(spike_times > 0.05) & (spike_times < duration_s - 0.05)]
        variable_name = f"CH1_Unit{index}"
        spike_units.append(
            SpikeUnit(
                name=variable_name,
                channel_id=1,
                unit_index=index,
                timestamps_count=len(spike_times),
                variable_name=variable_name,
                region="M1",
                channel_id_source="synthetic",
            )
        )
        spike_data[variable_name] = SpikeData(name=variable_name, timestamps_s=spike_times.astype(float))

    session = SessionData(
        file_path=Path("synthetic_population.nex5"),
        metadata={
            "duration_s": duration_s,
            "timestamp_frequency_hz": 30000.0,
            "start_time_s": 0.0,
            "end_time_s": duration_s,
        },
        lfp_channels=[lfp_channel],
        spike_units=spike_units,
        region_map=region_map,
        waveform_available=False,
    )
    store = InMemorySessionStore(
        session,
        lfp_data={
            "THETA_LFP": ContinuousData(
                name="THETA_LFP",
                sampling_rate_hz=sampling_rate_hz,
                values=lfp_values.astype(float),
                fragment_starts_s=np.asarray([0.0], dtype=float),
                fragment_lengths=np.asarray([len(lfp_values)], dtype=int),
            )
        },
        spike_data=spike_data,
    )
    return replace(session, data_store=store)


def _make_locked_spike_lfp_session() -> SessionData:
    sampling_rate_hz = 1000.0
    duration_s = 12.0
    theta_frequency_hz = 8.0
    time_axis = np.arange(0.0, duration_s, 1.0 / sampling_rate_hz)
    rng = np.random.default_rng(101)
    lfp_values = (
        np.sin(2 * np.pi * theta_frequency_hz * time_axis)
        + 0.15 * np.sin(2 * np.pi * 40.0 * time_axis)
        + 0.03 * rng.standard_normal(len(time_axis))
    )

    theta_period_s = 1.0 / theta_frequency_hz
    base_spike_times = np.arange(0.2, duration_s - 0.2, theta_period_s)
    spike_times = base_spike_times + rng.normal(0.0, 0.003, size=len(base_spike_times))
    spike_times = spike_times[(spike_times > 0.0) & (spike_times < duration_s)]

    lfp_channel = LFPChannel(
        name="LOCKED_LFP",
        channel_id=1,
        sample_rate_hz=sampling_rate_hz,
        duration_s=duration_s,
        variable_name="LOCKED_LFP",
        region="CA1",
        channel_id_source="synthetic",
    )
    spike_unit = SpikeUnit(
        name="CH1_Unit1",
        channel_id=1,
        unit_index=1,
        timestamps_count=len(spike_times),
        variable_name="CH1_Unit1",
        region="CA1",
        channel_id_source="synthetic",
    )
    session = SessionData(
        file_path=Path("synthetic_locked_spike_lfp.nex5"),
        metadata={
            "duration_s": duration_s,
            "timestamp_frequency_hz": 30000.0,
            "start_time_s": 0.0,
            "end_time_s": duration_s,
        },
        lfp_channels=[lfp_channel],
        spike_units=[spike_unit],
        region_map={1: "CA1"},
        waveform_available=False,
    )
    store = InMemorySessionStore(
        session,
        lfp_data={
            "LOCKED_LFP": ContinuousData(
                name="LOCKED_LFP",
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
            )
        },
    )
    return replace(session, data_store=store)


def _make_multi_unit_locked_spike_lfp_session() -> SessionData:
    sampling_rate_hz = 1000.0
    duration_s = 12.0
    theta_frequency_hz = 8.0
    time_axis = np.arange(0.0, duration_s, 1.0 / sampling_rate_hz)
    rng = np.random.default_rng(303)
    lfp_values = (
        np.sin(2 * np.pi * theta_frequency_hz * time_axis)
        + 0.15 * np.sin(2 * np.pi * 40.0 * time_axis)
        + 0.03 * rng.standard_normal(len(time_axis))
    )

    theta_period_s = 1.0 / theta_frequency_hz
    base_spike_times = np.arange(0.2, duration_s - 0.2, theta_period_s)
    first_spike_times = base_spike_times + rng.normal(0.0, 0.003, size=len(base_spike_times))
    second_spike_times = base_spike_times + theta_period_s / 3.0 + rng.normal(0.0, 0.003, size=len(base_spike_times))
    first_spike_times = first_spike_times[(first_spike_times > 0.0) & (first_spike_times < duration_s)]
    second_spike_times = second_spike_times[(second_spike_times > 0.0) & (second_spike_times < duration_s)]

    lfp_channel = LFPChannel(
        name="LOCKED_LFP",
        channel_id=1,
        sample_rate_hz=sampling_rate_hz,
        duration_s=duration_s,
        variable_name="LOCKED_LFP",
        region="CA1",
        channel_id_source="synthetic",
    )
    spike_units = [
        SpikeUnit(
            name="CH1_Unit1",
            channel_id=1,
            unit_index=1,
            timestamps_count=len(first_spike_times),
            variable_name="CH1_Unit1",
            region="CA1",
            channel_id_source="synthetic",
        ),
        SpikeUnit(
            name="CH1_Unit2",
            channel_id=1,
            unit_index=2,
            timestamps_count=len(second_spike_times),
            variable_name="CH1_Unit2",
            region="CA1",
            channel_id_source="synthetic",
        ),
    ]
    session = SessionData(
        file_path=Path("synthetic_multi_unit_locked_spike_lfp.nex5"),
        metadata={
            "duration_s": duration_s,
            "timestamp_frequency_hz": 30000.0,
            "start_time_s": 0.0,
            "end_time_s": duration_s,
        },
        lfp_channels=[lfp_channel],
        spike_units=spike_units,
        region_map={1: "CA1"},
        waveform_available=False,
    )
    store = InMemorySessionStore(
        session,
        lfp_data={
            "LOCKED_LFP": ContinuousData(
                name="LOCKED_LFP",
                sampling_rate_hz=sampling_rate_hz,
                values=lfp_values.astype(float),
                fragment_starts_s=np.asarray([0.0], dtype=float),
                fragment_lengths=np.asarray([len(lfp_values)], dtype=int),
            )
        },
        spike_data={
            "CH1_Unit1": SpikeData(
                name="CH1_Unit1",
                timestamps_s=np.asarray(first_spike_times, dtype=float),
            ),
            "CH1_Unit2": SpikeData(
                name="CH1_Unit2",
                timestamps_s=np.asarray(second_spike_times, dtype=float),
            ),
        },
    )
    return replace(session, data_store=store)


def _make_pairwise_lfp_session() -> SessionData:
    sampling_rate_hz = 1000.0
    duration_s = 10.0
    time_axis = np.arange(0.0, duration_s, 1.0 / sampling_rate_hz)
    rng = np.random.default_rng(404)
    first_values = np.sin(2 * np.pi * 8.0 * time_axis) + 0.03 * rng.standard_normal(len(time_axis))
    second_values = np.sin(2 * np.pi * 8.0 * time_axis + np.pi / 6.0) + 0.03 * rng.standard_normal(len(time_axis))

    first_channel = LFPChannel(
        name="LFP_CH1",
        channel_id=1,
        sample_rate_hz=sampling_rate_hz,
        duration_s=duration_s,
        variable_name="LFP_CH1",
        region="M1",
        channel_id_source="synthetic",
    )
    second_channel = LFPChannel(
        name="LFP_CH2",
        channel_id=2,
        sample_rate_hz=sampling_rate_hz,
        duration_s=duration_s,
        variable_name="LFP_CH2",
        region="S1",
        channel_id_source="synthetic",
    )
    session = SessionData(
        file_path=Path("synthetic_pairwise_lfp.nex5"),
        metadata={
            "duration_s": duration_s,
            "timestamp_frequency_hz": 30000.0,
            "start_time_s": 0.0,
            "end_time_s": duration_s,
        },
        lfp_channels=[first_channel, second_channel],
        spike_units=[],
        region_map={1: "M1", 2: "S1"},
        waveform_available=False,
    )
    store = InMemorySessionStore(
        session,
        lfp_data={
            "LFP_CH1": ContinuousData(
                name="LFP_CH1",
                sampling_rate_hz=sampling_rate_hz,
                values=first_values.astype(float),
                fragment_starts_s=np.asarray([0.0], dtype=float),
                fragment_lengths=np.asarray([len(first_values)], dtype=int),
            ),
            "LFP_CH2": ContinuousData(
                name="LFP_CH2",
                sampling_rate_hz=sampling_rate_hz,
                values=second_values.astype(float),
                fragment_starts_s=np.asarray([0.0], dtype=float),
                fragment_lengths=np.asarray([len(second_values)], dtype=int),
            ),
        },
        spike_data={},
    )
    return replace(session, data_store=store)


def _make_low_power_lfp_session() -> SessionData:
    sampling_rate_hz = 1000.0
    duration_s = 12.0
    time_axis = np.arange(0.0, duration_s, 1.0 / sampling_rate_hz)
    values = 1e-5 * np.sin(2 * np.pi * 8.0 * time_axis)

    channel = LFPChannel(
        name="LOW_POWER_LFP",
        channel_id=1,
        sample_rate_hz=sampling_rate_hz,
        duration_s=duration_s,
        variable_name="LOW_POWER_LFP",
        region="M1",
        channel_id_source="synthetic",
    )
    session = SessionData(
        file_path=Path("synthetic_low_power.nex5"),
        metadata={
            "duration_s": duration_s,
            "timestamp_frequency_hz": 30000.0,
            "start_time_s": 0.0,
            "end_time_s": duration_s,
        },
        lfp_channels=[channel],
        spike_units=[],
        region_map={1: "M1"},
        waveform_available=False,
    )
    store = InMemorySessionStore(
        session,
        lfp_data={
            "LOW_POWER_LFP": ContinuousData(
                name="LOW_POWER_LFP",
                sampling_rate_hz=sampling_rate_hz,
                values=values.astype(float),
                fragment_starts_s=np.asarray([0.0], dtype=float),
                fragment_lengths=np.asarray([len(values)], dtype=int),
            )
        },
        spike_data={},
    )
    return replace(session, data_store=store)


def test_psd_tracks_dominant_frequency() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    psd_node = root.find_node("lfp:psd:ch01")

    result = AnalysisService().compute(session, psd_node, profile, {})

    peak_frequency = float(result.export_table.loc[result.export_table["power_db"].idxmax(), "frequency_hz"])
    assert 7.0 <= peak_frequency <= 11.0
    assert result.y_label == "Power (dB)"
    assert {"power", "power_db"}.issubset(result.export_table.columns)


def test_psd_auto_expands_display_range_for_low_power_recordings() -> None:
    session = _make_low_power_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    psd_node = root.find_node("lfp:psd:ch01")

    result = AnalysisService().compute(session, psd_node, profile, {})

    lower, upper = result.meta["y_range"]
    power_db = result.export_table["power_db"].to_numpy(dtype=float)
    assert (lower, upper) != (-70.0, 0.0)
    assert lower <= float(np.nanpercentile(power_db, 1.0))
    assert upper >= float(np.nanpercentile(power_db, 99.0))


def test_psd_supports_custom_minimum_frequency_cutoff() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    psd_node = root.find_node("lfp:psd:ch01")

    result = AnalysisService().compute(session, psd_node, profile, {"min_freq_hz": 20.0, "max_freq_hz": 120.0})

    assert not result.export_table.empty
    assert float(result.export_table["frequency_hz"].min()) >= 20.0


def test_spectrogram_auto_expands_color_range_for_low_power_recordings() -> None:
    session = _make_low_power_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:spectrogram:ch01")

    result = AnalysisService().compute(session, node, profile, {})

    matrix = np.asarray(result.image, dtype=float)
    assert result.meta["vmin"] != -80.0
    assert result.meta["vmax"] != -20.0
    assert result.meta["vmin"] <= float(np.nanpercentile(matrix, 1.0))
    assert result.meta["vmax"] >= float(np.nanpercentile(matrix, 99.0))


def test_analysis_service_clone_preserves_cached_results() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:psd:ch01")
    service = AnalysisService()

    result = service.compute(session, node, profile, {})
    cloned = service.clone()

    assert cloned.compute(session, node, profile, {}) is result


def test_analysis_service_merge_cache_reuses_exported_results() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:psd:ch01")
    base_service = AnalysisService()
    export_service = base_service.clone()

    result = export_service.compute(session, node, profile, {})
    base_service.merge_cache(export_service)

    assert base_service.compute(session, node, profile, {}) is result


def test_lfp_tree_no_longer_exposes_fft_quick_look() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)

    with pytest.raises(KeyError):
        root.find_node("lfp:fft:ch01")


def test_bandpass_preview_returns_common_band_composite() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:bandpass_preview:ch01")

    result = AnalysisService().compute(session, node, profile, {"low_hz": 4.0, "high_hz": 12.0, "preview_duration_s": 5.0})

    assert result.kind == "composite"
    assert len(result.panels) == 6
    assert result.meta["layout"] == {"rows": 3, "cols": 2}
    assert [panel.title for panel in result.panels] == [
        "Custom (4.0-12.0 Hz)",
        "Delta (0.5-4.0 Hz)",
        "Theta (4.0-8.0 Hz)",
        "Alpha (8.0-13.0 Hz)",
        "Beta (13.0-30.0 Hz)",
        "Gamma (30.0-80.0 Hz)",
    ]
    assert {"panel", "time_s", "amplitude", "low_hz", "high_hz"}.issubset(result.export_table.columns)

    figure = create_publication_figure(result)
    assert len(figure.axes) == 6


def test_single_channel_pac_detects_known_coupling_band() -> None:
    session = _make_pac_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    pac_node = root.find_node("lfp:pac:ch01")

    result = AnalysisService().compute(session, pac_node, profile, {})

    assert result.kind == "heatmap"
    assert not result.export_table.empty
    peak_row, peak_col = np.unravel_index(np.nanargmax(result.export_table.to_numpy()), result.export_table.shape)
    peak_amp_hz = float(result.export_table.index[peak_row])
    peak_phase_hz = float(result.export_table.columns[peak_col])
    peak_mi = float(result.export_table.to_numpy()[peak_row, peak_col])

    assert 4.0 <= peak_phase_hz <= 8.0
    assert 60.0 <= peak_amp_hz <= 100.0
    assert peak_mi > 0.001


def test_pac_and_pac_polar_share_pac_state(monkeypatch) -> None:
    session = _make_pac_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    pac_node = root.find_node("lfp:pac:ch01")
    polar_node = root.find_node("lfp:pac_polar:ch01")
    service = AnalysisService()
    original = lfp_module._compute_pac_state
    calls = {"count": 0}

    def wrapped(values, sampling_rate_hz, params):
        calls["count"] += 1
        return original(values, sampling_rate_hz, params)

    monkeypatch.setattr(lfp_module, "_compute_pac_state", wrapped)

    service.compute(session, pac_node, profile, {})
    service.compute(session, polar_node, profile, {})

    assert calls["count"] == 1


def test_pac_polar_uses_peak_pair_for_phase_amplitude_distribution() -> None:
    session = _make_pac_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    polar_node = root.find_node("lfp:pac_polar:ch01")

    result = AnalysisService().compute(session, polar_node, profile, {})

    assert result.kind == "polar"
    assert not result.export_table.empty
    assert {
        "phase_left_rad",
        "phase_right_rad",
        "phase_center_rad",
        "mean_amplitude",
        "peak_phase_frequency_hz",
        "peak_amplitude_frequency_hz",
    }.issubset(result.export_table.columns)
    assert float(result.meta["peak_phase_hz"]) >= 4.0
    assert float(result.meta["peak_amp_hz"]) >= 60.0


def test_heatmap_rerender_keeps_single_colorbar_and_respects_color_limits() -> None:
    matrix = np.array(
        [
            [-72.0, -58.0, -49.0],
            [-61.0, -43.0, -34.0],
            [-55.0, -32.0, -21.0],
        ],
        dtype=float,
    )
    result = AnalysisResult(
        node_id="lfp:spectrogram:ch01",
        title="Spectrogram - ch01",
        kind="heatmap",
        x_label="Time (s)",
        y_label="Frequency (Hz)",
        color_label="Power (dB)",
        image=matrix,
        image_x=np.array([0.0, 0.5, 1.0], dtype=float),
        image_y=np.array([10.0, 20.0, 30.0], dtype=float),
        export_table=pd.DataFrame(matrix),
        meta={"vmin": -80.0, "vmax": -20.0},
    )
    figure = Figure()
    axis = figure.add_subplot(111)

    render_publication_axes(axis, result)
    assert len(figure.axes) == 2
    assert axis.images[0].get_clim() == (-80.0, -20.0)

    render_publication_axes(axis, result)
    assert len(figure.axes) == 2

    line_result = AnalysisResult(
        node_id="lfp:psd:ch01",
        title="PSD - ch01",
        kind="line",
        x_label="Frequency (Hz)",
        y_label="Power (dB)",
        export_table=pd.DataFrame({"frequency_hz": [1.0, 2.0, 3.0], "power_db": [-50.0, -30.0, -40.0]}),
    )
    render_publication_axes(axis, line_result)
    assert len(figure.axes) == 1


def test_heatmap_render_supports_custom_ranges_hidden_colorbar_and_colormap() -> None:
    matrix = np.array(
        [
            [-72.0, -58.0, -49.0],
            [-61.0, -43.0, -34.0],
            [-55.0, -32.0, -21.0],
        ],
        dtype=float,
    )
    result = AnalysisResult(
        node_id="lfp:spectrogram:ch01",
        title="Spectrogram - ch01",
        kind="heatmap",
        x_label="Time (s)",
        y_label="Frequency (Hz)",
        color_label="Power (dB)",
        image=matrix,
        image_x=np.array([0.0, 0.5, 1.0], dtype=float),
        image_y=np.array([10.0, 20.0, 30.0], dtype=float),
        export_table=pd.DataFrame(matrix),
        meta={
            "vmin": -80.0,
            "vmax": -20.0,
            "show_colorbar": False,
            "colormap": "viridis",
            "x_range": (0.2, 0.8),
            "y_range": (12.0, 28.0),
        },
    )
    figure = Figure()
    axis = figure.add_subplot(111)

    render_publication_axes(axis, result)

    assert len(figure.axes) == 1
    assert axis.images[0].get_cmap().name == "viridis"
    assert axis.get_xlim() == (0.2, 0.8)
    assert axis.get_ylim() == (12.0, 28.0)


def test_polar_render_supports_direction_tick_step_and_hidden_metrics_box() -> None:
    result = AnalysisResult(
        node_id="lfp:pac_polar:ch01",
        title="PAC Polar - ch01",
        kind="polar",
        export_table=pd.DataFrame(
            {
                "phase_left_rad": [0.0, np.pi / 2.0],
                "phase_right_rad": [np.pi / 2.0, np.pi],
                "phase_center_rad": [np.pi / 4.0, 3.0 * np.pi / 4.0],
                "mean_amplitude": [1.0, 2.0],
            }
        ),
        meta={
            "polar_zero_location": "E",
            "polar_direction": "counterclockwise",
            "polar_tick_step_deg": 90,
            "show_polar_grid": False,
            "show_metrics_box": False,
            "mean_phase_rad": 1.57,
            "plv": 0.8,
        },
    )
    figure = Figure()
    axis = figure.add_subplot(111, projection="polar")

    render_publication_axes(axis, result)

    tick_labels = [label.get_text() for label in axis.get_xticklabels()]
    assert tick_labels == ["0 deg", "90 deg", "180 deg", "270 deg"]
    assert len(axis.texts) == 0


def test_analysis_service_applies_custom_plot_overrides_to_line_results() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:psd:ch01")

    result = AnalysisService().compute(
        session,
        node,
        profile,
        {
            "plot_use_custom_x_range": True,
            "plot_x_min": 1.0,
            "plot_x_max": 40.0,
            "plot_use_custom_y_range": True,
            "plot_y_min": -90.0,
            "plot_y_max": -10.0,
            "plot_line_width": 3.5,
            "plot_show_legend": False,
        },
    )

    assert result.meta["x_range"] == (1.0, 40.0)
    assert result.meta["y_range"] == (-90.0, -10.0)
    assert result.meta["line_width"] == 3.5
    assert result.meta["show_legend"] is False


def test_analysis_service_applies_polar_and_metrics_overrides() -> None:
    session = _make_pac_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:pac_polar:ch01")

    result = AnalysisService().compute(
        session,
        node,
        profile,
        {
            "plot_polar_zero_location": "E",
            "plot_polar_direction": "counterclockwise",
            "plot_polar_tick_step_deg": 90,
            "plot_show_polar_grid": False,
            "plot_show_metrics_box": False,
        },
    )

    assert result.meta["polar_zero_location"] == "E"
    assert result.meta["polar_direction"] == "counterclockwise"
    assert result.meta["polar_tick_step_deg"] == 90
    assert result.meta["show_polar_grid"] is False
    assert result.meta["show_metrics_box"] is False


def test_numeric_heatmap_uses_real_axis_ranges_and_non_inverted_frequency_axis() -> None:
    matrix = np.array(
        [
            [-72.0, -58.0, -49.0],
            [-61.0, -43.0, -34.0],
            [-55.0, -32.0, -21.0],
        ],
        dtype=float,
    )
    result = AnalysisResult(
        node_id="lfp:spectrogram:ch01",
        title="Spectrogram - ch01",
        kind="heatmap",
        x_label="Time (s)",
        y_label="Frequency (Hz)",
        color_label="Power (dB)",
        image=matrix,
        image_x=np.array([0.0, 0.5, 1.0], dtype=float),
        image_y=np.array([10.0, 20.0, 30.0], dtype=float),
        export_table=pd.DataFrame(matrix),
        meta={"vmin": -80.0, "vmax": -20.0},
    )
    figure = Figure()
    axis = figure.add_subplot(111)

    render_publication_axes(axis, result)

    y_min, y_max = axis.get_ylim()
    x_min, x_max = axis.get_xlim()
    assert y_min < y_max
    assert y_min <= 10.0
    assert y_max >= 30.0
    assert x_min <= 0.0
    assert x_max >= 1.0


def test_psd_forwards_window_and_average_to_welch(monkeypatch) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:psd:ch01")
    captured: dict[str, object] = {}

    def fake_welch(values, **kwargs):
        captured.update(kwargs)
        return np.array([1.0, 2.0, 3.0], dtype=float), np.array([1.0, 0.5, 0.25], dtype=float)

    monkeypatch.setattr(lfp_module.signal, "welch", fake_welch)

    result = AnalysisService().compute(
        session,
        node,
        profile,
        {
            "window_function": "hamming",
            "welch_average": "median",
        },
    )

    assert captured["window"] == "hamming"
    assert captured["average"] == "median"
    assert not result.export_table.empty


def test_spectrogram_forwards_detrend_and_scaling(monkeypatch) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:spectrogram:ch01")
    captured: dict[str, object] = {}

    def fake_spectrogram(values, **kwargs):
        captured.update(kwargs)
        return (
            np.array([5.0, 10.0], dtype=float),
            np.array([0.0, 1.0], dtype=float),
            np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float),
        )

    monkeypatch.setattr(lfp_module.signal, "spectrogram", fake_spectrogram)

    result = AnalysisService().compute(
        session,
        node,
        profile,
        {
            "detrend_mode": "linear",
            "spectrum_scaling": "spectrum",
        },
    )

    assert captured["detrend"] == "linear"
    assert captured["scaling"] == "spectrum"
    assert result.kind == "heatmap"


def test_isi_histogram_returns_non_empty_result() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike:isi:unit_ch01_u01")

    result = AnalysisService().compute(session, node, profile, {})

    assert not result.export_table.empty
    assert set(result.export_table.columns) >= {"bin_left_s", "count"}


def test_waveform_characterization_summary_returns_3d_cell_type_clusters() -> None:
    session = make_waveform_population_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike:waveform_characterization:summary")

    result = AnalysisService().compute(session, node, profile, {})

    assert result.kind == "scatter3d"
    assert result.x_label == "Half Width (ms)"
    assert result.y_label == "Firing Rate (Hz)"
    assert result.z_label == "Trough-to-Peak Width (ms)"
    assert {
        "unit",
        "half_width_ms",
        "firing_rate_hz",
        "trough_to_peak_ms",
        "putative_cell_type",
        "cluster_id",
        "color_hex",
    }.issubset(result.export_table.columns)
    assert set(result.export_table["putative_cell_type"]) == {"Putative excitatory", "Putative inhibitory"}
    assert result.export_table.groupby("putative_cell_type")["color_hex"].nunique().eq(1).all()


def test_waveform_characterization_summary_supports_selectable_xyz_features() -> None:
    session = make_waveform_population_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike:waveform_characterization:summary")

    result = AnalysisService().compute(
        session,
        node,
        profile,
        {
            "summary_x_feature": "snr",
            "summary_y_feature": "peak_to_trough_ratio",
            "summary_z_feature": "half_width_ms",
        },
    )

    assert result.kind == "scatter3d"
    assert result.x_label == "SNR"
    assert result.y_label == "Peak/Trough Ratio"
    assert result.z_label == "Half Width (ms)"
    assert result.meta["x_feature"] == "snr"
    assert result.meta["y_feature"] == "peak_to_trough_ratio"
    assert result.meta["z_feature"] == "half_width_ms"


def test_waveform_characterization_includes_individual_waveforms_and_mean() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike:waveform_characterization:unit_ch01_u01")

    result = AnalysisService().compute(session, node, profile, {})

    assert result.kind == "line"
    assert result.meta["n_displayed"] == result.meta["n_waveforms"]
    assert result.export_table["series"].iloc[0] == "Mean"
    assert result.export_table["series"].nunique() > 1
    mean_rows = result.export_table[result.export_table["series"] == "Mean"]
    sample_rows = result.export_table[result.export_table["series"] != "Mean"]
    assert mean_rows["ci_low"].notna().all()
    assert sample_rows["ci_low"].isna().all()


def test_population_coding_summary_returns_phase_raster_for_reference_lfp() -> None:
    session = _make_population_coding_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:population_coding:ch01")

    result = AnalysisService().compute(session, node, profile, {})

    assert result.kind == "phase_raster"
    assert {"unit_label", "unit_order", "cycle_index", "phase_deg", "x_deg", "spike_time_s"}.issubset(
        result.export_table.columns
    )
    assert result.export_table["unit_label"].nunique() == 3
    assert result.export_table["cycle_index"].nunique() >= 8
    assert result.export_table["phase_deg"].between(0.0, 360.0).all()


def test_population_coding_supports_alternate_unit_sort_modes() -> None:
    session = _make_population_coding_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:population_coding:ch01")
    service = AnalysisService()

    desc = service.compute(session, node, profile, {"unit_sort_mode": "phase_desc"})
    asc = service.compute(session, node, profile, {"unit_sort_mode": "phase_asc"})

    desc_first = desc.export_table.sort_values(["unit_order", "x_deg"]).iloc[0]["unit_label"]
    asc_first = asc.export_table.sort_values(["unit_order", "x_deg"]).iloc[0]["unit_label"]

    assert desc_first != asc_first


def test_phase_raster_render_can_hide_wave_overlay() -> None:
    session = _make_population_coding_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:population_coding:ch01")

    result = AnalysisService().compute(
        session,
        node,
        profile,
        {
            "plot_wave_overlay": False,
            "plot_cycle_line_alpha": 0.2,
        },
    )
    figure = Figure()
    axis = figure.add_subplot(111)

    render_publication_axes(axis, result)

    displayed_cycles = int(result.meta["displayed_cycles"])
    assert len(axis.lines) == displayed_cycles + 1


def test_spike_rate_power_metrics_returns_composite_spectrogram_and_psd() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike:rate_power_metrics:unit_ch01_u01")

    result = AnalysisService().compute(session, node, profile, {})

    assert result.kind == "composite"
    assert len(result.panels) == 2
    assert [panel.kind for panel in result.panels] == ["heatmap", "line"]
    assert {"panel", "time_s", "frequency_hz", "power_db"}.issubset(result.export_table.columns)
    psd_rows = result.export_table[result.export_table["panel"] == "psd"]
    peak_frequency = float(psd_rows.loc[psd_rows["power_db"].idxmax(), "frequency_hz"])
    assert 6.0 <= peak_frequency <= 10.0


def test_firing_rate_and_rate_power_metrics_share_cached_rate_trace_when_rate_params_match(monkeypatch) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    firing_rate_node = root.find_node("spike:firing_rate:unit_ch01_u01")
    metrics_node = root.find_node("spike:rate_power_metrics:unit_ch01_u01")
    service = AnalysisService()
    original = spike_module._build_rate_trace_state
    calls = {"count": 0}
    shared_rate_params = {"bin_size_ms": 25.0, "smoothing_sigma_ms": 5.0}

    def wrapped(runtime, node, params):
        calls["count"] += 1
        return original(runtime, node, params)

    monkeypatch.setattr(spike_module, "_build_rate_trace_state", wrapped)

    service.compute(session, firing_rate_node, profile, shared_rate_params)
    service.compute(session, metrics_node, profile, shared_rate_params)

    assert calls["count"] == 1


def test_create_publication_figure_supports_composite_and_phase_raster_results() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    service = AnalysisService()

    composite = service.compute(session, root.find_node("spike:rate_power_metrics:unit_ch01_u01"), profile, {})
    composite_figure = create_publication_figure(composite)
    assert len(composite_figure.axes) == 3

    population = service.compute(_make_population_coding_session(), AnalysisTreeBuilder().build(_make_population_coding_session(), profile).find_node("spike_lfp:population_coding:ch01"), profile, {})
    raster_figure = create_publication_figure(population)
    assert len(raster_figure.axes) == 1


def test_create_publication_figure_supports_scatter3d_results() -> None:
    session = make_waveform_population_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    result = AnalysisService().compute(session, root.find_node("spike:waveform_characterization:summary"), profile, {})

    figure = create_publication_figure(result)

    assert len(figure.axes) == 1
    assert figure.axes[0].name == "3d"


def test_create_publication_figure_places_polar_metrics_and_legend_outside_plot_area() -> None:
    result = AnalysisResult(
        node_id="lfp:pac_polar:ch05",
        title="PAC Polar - ch05(M1)",
        kind="polar",
        series=[
            PlotSeries(
                label="ch05(M1)",
                x=np.deg2rad(np.arange(0, 360, 45, dtype=float)),
                y=np.array([0.0080, 0.0092, 0.0068, 0.0079, 0.0087, 0.0101, 0.0094, 0.0086], dtype=float),
            )
        ],
        meta={
            "peak_phase_hz": 2.0,
            "peak_amp_hz": 120.0,
            "peak_mi": 0.002,
        },
    )

    figure = create_publication_figure(result)
    renderer = _draw_renderer(figure)
    axis = figure.axes[0]
    metrics_box = _metrics_artist(axis)

    assert not metrics_box.get_window_extent(renderer).overlaps(axis.get_window_extent(renderer))
    assert axis.get_legend() is not None
    assert not axis.get_legend().get_window_extent(renderer).overlaps(axis.get_window_extent(renderer))


def test_create_publication_figure_places_heatmap_metrics_box_away_from_image_and_colorbar() -> None:
    matrix = np.array(
        [
            [0.1, 0.4, 0.7],
            [0.2, 0.5, 0.8],
            [0.3, 0.6, 0.9],
        ],
        dtype=float,
    )
    result = AnalysisResult(
        node_id="lfp:pac:ch01",
        title="PAC Heatmap - ch01",
        kind="heatmap",
        x_label="Phase Frequency (Hz)",
        y_label="Amplitude Frequency (Hz)",
        color_label="MI",
        image=matrix,
        image_x=np.array([2.0, 4.0, 6.0], dtype=float),
        image_y=np.array([40.0, 80.0, 120.0], dtype=float),
        export_table=pd.DataFrame(matrix),
        meta={
            "peak_phase_hz": 4.0,
            "peak_amp_hz": 80.0,
            "peak_mi": 0.009,
            "show_colorbar": True,
        },
    )

    figure = create_publication_figure(result)
    renderer = _draw_renderer(figure)
    image_axis = figure.axes[0]
    colorbar_axis = next(axis for axis in figure.axes if axis is not image_axis)
    metrics_box = _metrics_artist(image_axis)
    metrics_bbox = metrics_box.get_window_extent(renderer)

    assert not metrics_bbox.overlaps(image_axis.get_window_extent(renderer))
    assert not metrics_bbox.overlaps(colorbar_axis.get_window_extent(renderer))


def test_create_publication_figure_places_line_legend_outside_plot_area() -> None:
    result = AnalysisResult(
        node_id="lfp:psd:multi",
        title="PSD Comparison",
        kind="line",
        x_label="Frequency (Hz)",
        y_label="Power (dB)",
        series=[
            PlotSeries(label="Condition A", x=np.array([1.0, 2.0, 3.0]), y=np.array([-10.0, -8.0, -7.0])),
            PlotSeries(label="Condition B", x=np.array([1.0, 2.0, 3.0]), y=np.array([-12.0, -9.0, -8.5])),
        ],
        meta={"show_legend": True},
    )

    figure = create_publication_figure(result)
    renderer = _draw_renderer(figure)
    axis = figure.axes[0]

    assert axis.get_legend() is not None
    assert not axis.get_legend().get_window_extent(renderer).overlaps(axis.get_window_extent(renderer))


def test_phase_locking_polar_places_metrics_box_outside_plot_area() -> None:
    session = _make_locked_spike_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:phase_locking_polar:unit_ch01_u01__ch01")
    result = AnalysisService().compute(session, node, profile, {})

    figure = create_publication_figure(result)
    renderer = _draw_renderer(figure)
    axis = figure.axes[0]
    metrics_box = _metrics_artist(axis)

    assert not metrics_box.get_window_extent(renderer).overlaps(axis.get_window_extent(renderer))


def test_spike_lfp_coherence_report_polar_panel_places_metrics_box_outside_plot_area() -> None:
    session = _make_locked_spike_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:coherence_report:unit_ch01_u01__ch01")
    result = AnalysisService().compute(
        session,
        node,
        profile,
        {"surrogate_runs": 12, "alpha": 0.05, "min_shift_s": 0.5},
    )

    figure = create_publication_figure(result)
    renderer = _draw_renderer(figure)
    polar_axis = next(axis for axis in figure.axes if axis.name == "polar")
    metrics_box = _metrics_artist(polar_axis)

    assert not metrics_box.get_window_extent(renderer).overlaps(polar_axis.get_window_extent(renderer))


def test_phase_locking_polar_returns_polar_histogram_for_spike_lfp_pair() -> None:
    session = _make_locked_spike_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:phase_locking_polar:unit_ch01_u01__ch01")

    result = AnalysisService().compute(session, node, profile, {})

    assert result.kind == "polar"
    assert {
        "phase_left_rad",
        "phase_right_rad",
        "phase_center_rad",
        "count",
    }.issubset(result.export_table.columns)
    assert float(result.meta["plv"]) > 0.3


def test_phase_locking_reuses_cached_lfp_phase_signal_across_units(monkeypatch) -> None:
    session = _make_multi_unit_locked_spike_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    first_node = root.find_node("spike_lfp:phase_locking:unit_ch01_u01__ch01")
    second_node = root.find_node("spike_lfp:phase_locking:unit_ch01_u02__ch01")
    service = AnalysisService()
    original = spike_lfp_module._build_phase_signal_state
    calls = {"count": 0}

    def wrapped(runtime, node, params):
        calls["count"] += 1
        return original(runtime, node, params)

    monkeypatch.setattr(spike_lfp_module, "_build_phase_signal_state", wrapped)

    service.compute(session, first_node, profile, {})
    service.compute(session, second_node, profile, {})

    assert calls["count"] == 1


def test_sfc_prebins_spike_train_without_rounding_tolerance(monkeypatch) -> None:
    session = _make_locked_spike_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:sfc:unit_ch01_u01__ch01")
    captured: dict[str, object] = {}

    def fake_spike_field_coherence(signal, spiketrain, **kwargs):
        captured["spiketrain"] = spiketrain
        return np.asarray([[0.25], [0.5]], dtype=float) * pq.dimensionless, np.asarray([6.0, 8.0], dtype=float) * pq.Hz

    monkeypatch.setattr(spike_lfp_module, "spike_field_coherence", fake_spike_field_coherence)

    result = AnalysisService().compute(session, node, profile, {})

    assert isinstance(captured["spiketrain"], BinnedSpikeTrain)
    assert captured["spiketrain"].tolerance is None
    assert {"frequency_hz", "coherence"}.issubset(result.export_table.columns)


def test_sfc_significance_and_coherence_report_share_surrogate_state(monkeypatch) -> None:
    session = _make_locked_spike_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    significance_node = root.find_node("spike_lfp:sfc_significance:unit_ch01_u01__ch01")
    report_node = root.find_node("spike_lfp:coherence_report:unit_ch01_u01__ch01")
    service = AnalysisService()
    original = spike_lfp_module._build_sfc_significance_state
    calls = {"count": 0}

    def wrapped(runtime, node, params):
        calls["count"] += 1
        return original(runtime, node, params)

    monkeypatch.setattr(spike_lfp_module, "_build_sfc_significance_state", wrapped)

    service.compute(session, significance_node, profile, {"surrogate_runs": 8, "alpha": 0.05, "min_shift_s": 0.5})
    service.compute(session, report_node, profile, {"surrogate_runs": 8, "alpha": 0.05, "min_shift_s": 0.5})

    assert calls["count"] == 1


def test_sta_and_coherence_report_share_sta_state(monkeypatch) -> None:
    session = _make_locked_spike_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    sta_node = root.find_node("spike_lfp:sta:unit_ch01_u01__ch01")
    report_node = root.find_node("spike_lfp:coherence_report:unit_ch01_u01__ch01")
    service = AnalysisService()
    original = spike_lfp_module._build_sta_state
    calls = {"count": 0}

    def wrapped(runtime, node, params):
        calls["count"] += 1
        return original(runtime, node, params)

    monkeypatch.setattr(spike_lfp_module, "_build_sta_state", wrapped)

    service.compute(session, sta_node, profile, {})
    service.compute(session, report_node, profile, {"surrogate_runs": 8, "alpha": 0.05, "min_shift_s": 0.5})

    assert calls["count"] == 1


def test_lfp_pair_coherence_and_region_summary_share_pair_state(monkeypatch) -> None:
    session = _make_pairwise_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    coherence_node = root.find_node("lfp_lfp:coherence:ch01__ch02")
    region_summary_node = root.find_node("lfp_lfp:region_summary:matrix")
    service = AnalysisService()
    original = lfp_lfp_module._build_pair_coherence_state
    calls = {"count": 0}

    def wrapped(runtime, first_variable_name, second_variable_name, params):
        calls["count"] += 1
        return original(runtime, first_variable_name, second_variable_name, params)

    monkeypatch.setattr(lfp_lfp_module, "_build_pair_coherence_state", wrapped)

    service.compute(session, coherence_node, profile, {})
    service.compute(session, region_summary_node, profile, {})

    assert calls["count"] == 1


def test_lfp_region_summary_separates_same_region_across_subjects() -> None:
    session = _make_pairwise_lfp_session().with_region_map(
        {
            1: {"subject": "Mouse A", "region": "M1"},
            2: {"subject": "Mouse B", "region": "M1"},
        }
    )
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp_lfp:region_summary:matrix")

    result = AnalysisService().compute(session, node, profile, {})

    assert result.export_table.index.tolist() == ["Mouse A / M1", "Mouse B / M1"]
    assert result.export_table.columns.tolist() == ["Mouse A / M1", "Mouse B / M1"]
    assert not pd.isna(result.export_table.loc["Mouse A / M1", "Mouse B / M1"])


def test_population_coding_same_region_only_does_not_fall_back_across_subjects() -> None:
    base_session = _make_population_coding_session()
    session = replace(
        base_session,
        lfp_channels=[
            replace(base_session.lfp_channels[0], subject="Mouse A", region="M1")
        ],
        spike_units=[
            replace(unit, channel_id=2, subject="Mouse B", region="M1")
            for unit in base_session.spike_units
        ],
        region_map={
            1: {"subject": "Mouse A", "region": "M1"},
            2: {"subject": "Mouse B", "region": "M1"},
        },
    )
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:population_coding:ch01")

    result = AnalysisService().compute(session, node, profile, {"same_region_only": True})

    assert result.kind == "message"
    assert "No units met" in (result.message or "")


def test_sfc_significance_returns_log_p_curve_and_threshold() -> None:
    session = _make_locked_spike_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:sfc_significance:unit_ch01_u01__ch01")

    result = AnalysisService().compute(
        session,
        node,
        profile,
        {"surrogate_runs": 24, "alpha": 0.05, "min_shift_s": 0.5},
    )

    assert result.kind == "line"
    assert {
        "frequency_hz",
        "negative_log10_pvalue",
        "negative_log10_threshold",
    }.issubset(result.export_table.columns)
    significant_rows = result.export_table[
        result.export_table["negative_log10_pvalue"] >= result.export_table["negative_log10_threshold"]
    ]
    theta_rows = significant_rows[
        significant_rows["frequency_hz"].between(6.0, 10.0) & (significant_rows["coherence"] >= 0.2)
    ]
    assert not theta_rows.empty


def test_spike_lfp_coherence_report_returns_four_panel_grid_composite() -> None:
    session = _make_locked_spike_lfp_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:coherence_report:unit_ch01_u01__ch01")

    result = AnalysisService().compute(
        session,
        node,
        profile,
        {"surrogate_runs": 16, "alpha": 0.05, "min_shift_s": 0.5},
    )

    assert result.kind == "composite"
    assert len(result.panels) == 4
    assert [panel.kind for panel in result.panels] == ["polar", "line", "line", "line"]
    assert result.meta["layout"] == {"rows": 2, "cols": 2}

    figure = create_publication_figure(result)
    assert len(figure.axes) == 4


def test_tree_builder_adds_placeholder_nodes_when_lfp_missing(sample_nex5_path) -> None:
    from nex5_analyzer.io.nex5_loader import Nex5SessionLoader

    session = Nex5SessionLoader().inspect(sample_nex5_path)
    root = AnalysisTreeBuilder().build(session, SessionProfile.default())

    lfp_root = root.find_node("category:lfp")
    assert any(child.kind == "placeholder" for child in lfp_root.children)


def test_sta_export_includes_confidence_band_columns() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:sta:unit_ch01_u01__ch01")

    result = AnalysisService().compute(session, node, profile, {})

    assert result.kind == "line"
    assert {"lag_ms", "amplitude", "sem", "ci_low", "ci_high"}.issubset(result.export_table.columns)
    finite = result.export_table["sem"].to_numpy(dtype=float)
    assert np.all(finite[np.isfinite(finite)] >= 0.0)
    assert "SEM" in result.y_label


def test_sta_sem_decreases_with_more_spikes() -> None:
    rng = np.random.default_rng(3)
    times = np.linspace(0.0, 10.0, 10_000)
    values = rng.standard_normal(times.size)
    lags_s = np.linspace(-0.02, 0.02, 41)
    few = np.linspace(1.0, 2.0, 5)
    many = np.linspace(1.0, 9.0, 400)

    sem_few, used_few = spike_lfp_module._sta_sem(values, times, few, lags_s)
    sem_many, used_many = spike_lfp_module._sta_sem(values, times, many, lags_s)

    assert used_few == 5 and used_many == 400
    assert np.nanmean(sem_many) < np.nanmean(sem_few)


def test_lfp_coherence_resamples_to_common_rate() -> None:
    values = np.sin(np.linspace(0.0, 20.0, 2000))
    same = lfp_lfp_module._resample_to_rate(values, 1000.0, 1000.0)
    halved = lfp_lfp_module._resample_to_rate(values, 1000.0, 500.0)

    assert np.array_equal(same, values)
    assert abs(halved.size - values.size // 2) <= 2


def test_cluster_silhouette_separates_clear_clusters() -> None:
    features = np.array([[0.0, 0.0], [0.1, 0.1], [5.0, 5.0], [5.1, 4.9]])
    labels = np.array([0, 0, 1, 1])
    mixed_labels = np.array([0, 1, 0, 1])

    assert spike_module._cluster_silhouette(features, labels) > 0.8
    assert spike_module._cluster_silhouette(features, mixed_labels) < spike_module.CLUSTER_SILHOUETTE_THRESHOLD


def test_pac_meta_reports_surrogate_significance() -> None:
    session = _make_pac_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:pac:ch01")

    result = AnalysisService().compute(session, node, profile, {"pac_surrogate_runs": 80})

    assert "peak_mi_z" in result.meta and "peak_mi_p" in result.meta
    p_value = float(result.meta["peak_mi_p"])
    assert 0.0 < p_value <= 1.0
    # p must be quantised to the surrogate count (Monte-Carlo permutation estimate).
    assert np.isclose(p_value * 81.0, round(p_value * 81.0))


def test_pac_bandwidth_meta_warns_when_amplitude_band_too_narrow() -> None:
    narrow_state = {
        "peak_indices": (0, 0),
        "phase_centers": np.array([8.0]),
        "amp_bandwidth_hz": 4.0,
    }
    wide_state = {
        "peak_indices": (0, 0),
        "phase_centers": np.array([8.0]),
        "amp_bandwidth_hz": 30.0,
    }

    assert "pac_bandwidth_warning" in lfp_module._pac_bandwidth_meta(narrow_state)
    assert lfp_module._pac_bandwidth_meta(wide_state) == {}


def test_phase_locking_histogram_uses_radian_axis_metadata() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:phase_locking:unit_ch01_u01__ch01")

    result = AnalysisService().compute(session, node, profile, {})
    assert result.meta.get("phase_axis") is True

    figure = Figure()
    axis = figure.add_subplot(111)
    render_publication_axes(axis, result)
    tick_labels = [label.get_text() for label in axis.get_xticklabels()]
    assert tick_labels == ["\u2212\u03c0", "\u2212\u03c0/2", "0", "\u03c0/2", "\u03c0"]


def test_sfc_significance_meta_enables_overlay() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:sfc_significance:unit_ch01_u01__ch01")

    result = AnalysisService().compute(session, node, profile, {})

    assert result.meta.get("significance_overlay") is True
    assert np.isfinite(float(result.meta.get("peak_frequency_hz", float("nan"))))
    figure = Figure()
    axis = figure.add_subplot(111)
    render_publication_axes(axis, result)


def test_sfc_significance_line_plots_log_p_not_coherence() -> None:
    # The SFC-significance export table carries both ``coherence`` and
    # ``negative_log10_pvalue``. The y-axis label, threshold line and
    # significance shading are all in -log10(p), so the plotted line must use
    # -log10(p) rather than coherence to stay self-consistent.
    from nex5_analyzer.plotting import _line_frame_from_result

    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike_lfp:sfc_significance:unit_ch01_u01__ch01")

    result = AnalysisService().compute(session, node, profile, {})
    table = result.export_table
    assert {"coherence", "negative_log10_pvalue"}.issubset(table.columns)

    frame = _line_frame_from_result(result)
    np.testing.assert_allclose(
        frame["y"].to_numpy(dtype=float),
        table["negative_log10_pvalue"].to_numpy(dtype=float),
    )
