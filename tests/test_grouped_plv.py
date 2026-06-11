from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg

from nex5_analyzer.config import SessionProfile
from nex5_analyzer.grouped_plv import GroupedPLVManifestEntry, GroupedPLVParams, GroupedPLVRunner
from nex5_analyzer.plotting import create_publication_figure
from nex5_analyzer.testing import InMemorySessionStore
from nex5_analyzer.models import ContinuousData, LFPChannel, SessionData, SpikeData, SpikeUnit


class FakeLoader:
    def __init__(self, sessions_by_path: dict[Path, SessionData]) -> None:
        self._sessions_by_path = {Path(path): session for path, session in sessions_by_path.items()}

    def inspect(self, file_path, manual_channel_ids=None, region_map=None):
        session = self._sessions_by_path[Path(file_path)]
        return replace(session, file_path=Path(file_path))


def _make_grouped_plv_session(
    file_name: str,
    *,
    unit_phase_offsets_deg: list[float],
    region: str = "CA1",
) -> SessionData:
    sampling_rate_hz = 1000.0
    duration_s = 12.0
    theta_frequency_hz = 8.0
    time_axis = np.arange(0.0, duration_s, 1.0 / sampling_rate_hz)
    lfp_values = np.sin(2.0 * np.pi * theta_frequency_hz * time_axis)
    theta_period_s = 1.0 / theta_frequency_hz
    cycle_starts = np.arange(0.2, duration_s - 0.2, theta_period_s)

    lfp_channel = LFPChannel(
        name="LOCKED_LFP",
        channel_id=1,
        sample_rate_hz=sampling_rate_hz,
        duration_s=duration_s,
        variable_name="LOCKED_LFP",
        region=region,
        channel_id_source="synthetic",
    )

    spike_units: list[SpikeUnit] = []
    spike_data: dict[str, SpikeData] = {}
    for index, phase_deg in enumerate(unit_phase_offsets_deg, start=1):
        spike_times = cycle_starts + (float(phase_deg) / 360.0) * theta_period_s
        spike_times = spike_times[(spike_times > 0.05) & (spike_times < duration_s - 0.05)]
        variable_name = f"CH1_Unit{index}"
        spike_units.append(
            SpikeUnit(
                name=variable_name,
                channel_id=1,
                unit_index=index,
                timestamps_count=len(spike_times),
                variable_name=variable_name,
                region=region,
                channel_id_source="synthetic",
            )
        )
        spike_data[variable_name] = SpikeData(name=variable_name, timestamps_s=np.asarray(spike_times, dtype=float))

    session = SessionData(
        file_path=Path(file_name),
        metadata={
            "duration_s": duration_s,
            "timestamp_frequency_hz": 30000.0,
            "start_time_s": 0.0,
            "end_time_s": duration_s,
        },
        lfp_channels=[lfp_channel],
        spike_units=spike_units,
        region_map={1: region},
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
        spike_data=spike_data,
    )
    return replace(session, data_store=store)


def _group_mean_at_nearest_phase(group_level: pd.DataFrame, phase_deg: float) -> float:
    row = group_level.iloc[(group_level["phase_deg"] - phase_deg).abs().argsort()[:1]]
    return float(row["mean"].iloc[0])


def _draw_renderer(figure):
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    return canvas.get_renderer()


def test_grouped_plv_runner_requires_manifest_columns(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.csv"
    pd.DataFrame({"file_path": ["a.nex5"]}).to_csv(manifest_path, index=False)

    runner = GroupedPLVRunner(loader=FakeLoader({}))

    with pytest.raises(ValueError, match="group"):
        runner.load_manifest(manifest_path)


def test_grouped_plv_runner_averages_subjects_before_groups() -> None:
    first_path = Path("subject_a.nex5")
    second_path = Path("subject_b.nex5")
    sessions = {
        first_path: _make_grouped_plv_session("subject_a.nex5", unit_phase_offsets_deg=[0.0]),
        second_path: _make_grouped_plv_session("subject_b.nex5", unit_phase_offsets_deg=[180.0, 180.0, 180.0]),
    }
    runner = GroupedPLVRunner(loader=FakeLoader(sessions))
    entries = [
        GroupedPLVManifestEntry(file_path=first_path, group="trained", subject="Mouse A"),
        GroupedPLVManifestEntry(file_path=second_path, group="trained", subject="Mouse B"),
    ]

    result = runner.run_entries(
        entries,
        SessionProfile.default(),
        GroupedPLVParams(phase_bins=12, align_preferred_phase=False, min_spikes_per_unit=1),
    )

    trained_subjects = result.subject_level[result.subject_level["group"] == "trained"]
    trained_group = result.group_level[result.group_level["group"] == "trained"]
    manual_subject_mean = (
        trained_subjects.groupby("phase_deg", as_index=False)["mean_probability"].mean().rename(columns={"mean_probability": "expected"})
    )
    merged = trained_group.merge(manual_subject_mean, on="phase_deg", how="inner")

    assert result.preview_result.kind == "polar"
    assert np.allclose(merged["mean"], merged["expected"])
    assert _group_mean_at_nearest_phase(trained_group, 0.0) == pytest.approx(
        _group_mean_at_nearest_phase(trained_group, 180.0),
        rel=0.08,
    )


def test_grouped_plv_runner_aligns_preferred_phase_when_enabled() -> None:
    first_path = Path("aligned_a.nex5")
    second_path = Path("aligned_b.nex5")
    sessions = {
        first_path: _make_grouped_plv_session("aligned_a.nex5", unit_phase_offsets_deg=[0.0]),
        second_path: _make_grouped_plv_session("aligned_b.nex5", unit_phase_offsets_deg=[180.0]),
    }
    runner = GroupedPLVRunner(loader=FakeLoader(sessions))
    entries = [
        GroupedPLVManifestEntry(file_path=first_path, group="trained", subject="Mouse A"),
        GroupedPLVManifestEntry(file_path=second_path, group="trained", subject="Mouse B"),
    ]

    unaligned = runner.run_entries(
        entries,
        SessionProfile.default(),
        GroupedPLVParams(phase_bins=18, align_preferred_phase=False, min_spikes_per_unit=1),
    )
    aligned = runner.run_entries(
        entries,
        SessionProfile.default(),
        GroupedPLVParams(phase_bins=18, align_preferred_phase=True, min_spikes_per_unit=1),
    )

    unaligned_group = unaligned.group_level[unaligned.group_level["group"] == "trained"]
    aligned_group = aligned.group_level[aligned.group_level["group"] == "trained"]

    assert _group_mean_at_nearest_phase(aligned_group, 0.0) > _group_mean_at_nearest_phase(unaligned_group, 0.0)


def test_grouped_plv_runner_only_shades_confidence_band_for_multiple_subjects() -> None:
    multi_paths = [Path("multi_a.nex5"), Path("multi_b.nex5")]
    multi_sessions = {
        multi_paths[0]: _make_grouped_plv_session("multi_a.nex5", unit_phase_offsets_deg=[0.0]),
        multi_paths[1]: _make_grouped_plv_session("multi_b.nex5", unit_phase_offsets_deg=[10.0]),
    }
    single_path = Path("single_a.nex5")
    single_sessions = {
        single_path: _make_grouped_plv_session("single_a.nex5", unit_phase_offsets_deg=[0.0]),
    }
    params = GroupedPLVParams(phase_bins=18, align_preferred_phase=True, min_spikes_per_unit=1)

    multi_result = GroupedPLVRunner(loader=FakeLoader(multi_sessions)).run_entries(
        [
            GroupedPLVManifestEntry(file_path=multi_paths[0], group="trained", subject="Mouse A"),
            GroupedPLVManifestEntry(file_path=multi_paths[1], group="trained", subject="Mouse B"),
        ],
        SessionProfile.default(),
        params,
    )
    single_result = GroupedPLVRunner(loader=FakeLoader(single_sessions)).run_entries(
        [
            GroupedPLVManifestEntry(file_path=single_path, group="trained", subject="Mouse Solo"),
        ],
        SessionProfile.default(),
        params,
    )

    multi_figure = create_publication_figure(multi_result.preview_result)
    single_figure = create_publication_figure(single_result.preview_result)
    multi_alphas = [collection.get_alpha() for collection in multi_figure.axes[0].collections]
    single_alphas = [collection.get_alpha() for collection in single_figure.axes[0].collections]

    assert multi_figure.axes[0].name == "polar"
    assert multi_result.group_level["ci_low"].notna().any()
    assert any(alpha == pytest.approx(0.10) for alpha in multi_alphas if alpha is not None)
    assert single_result.group_level["ci_low"].isna().all()
    assert all(alpha != pytest.approx(0.10) for alpha in single_alphas if alpha is not None)


def test_grouped_plv_runner_uses_composite_polar_preview_for_multiple_regions() -> None:
    first_path = Path("ca1_a.nex5")
    second_path = Path("ec_a.nex5")
    sessions = {
        first_path: _make_grouped_plv_session("ca1_a.nex5", unit_phase_offsets_deg=[0.0], region="CA1"),
        second_path: _make_grouped_plv_session("ec_a.nex5", unit_phase_offsets_deg=[45.0], region="EC"),
    }
    runner = GroupedPLVRunner(loader=FakeLoader(sessions))
    result = runner.run_entries(
        [
            GroupedPLVManifestEntry(file_path=first_path, group="trained", subject="Mouse A", region="CA1"),
            GroupedPLVManifestEntry(file_path=second_path, group="trained", subject="Mouse B", region="EC"),
        ],
        SessionProfile.default(),
        GroupedPLVParams(phase_bins=18, align_preferred_phase=True, min_spikes_per_unit=1, same_region_only=False),
    )

    figure = create_publication_figure(result.preview_result)

    assert result.preview_result.kind == "composite"
    assert [panel.kind for panel in result.preview_result.panels] == ["polar", "polar"]
    assert len(figure.axes) == 2
    assert all(axis.name == "polar" for axis in figure.axes)


def test_grouped_plv_single_region_preview_places_legend_outside_plot_area() -> None:
    first_path = Path("group_a_1.nex5")
    second_path = Path("group_b_1.nex5")
    sessions = {
        first_path: _make_grouped_plv_session("group_a_1.nex5", unit_phase_offsets_deg=[0.0]),
        second_path: _make_grouped_plv_session("group_b_1.nex5", unit_phase_offsets_deg=[90.0]),
    }
    runner = GroupedPLVRunner(loader=FakeLoader(sessions))
    result = runner.run_entries(
        [
            GroupedPLVManifestEntry(file_path=first_path, group="trained", subject="Mouse A"),
            GroupedPLVManifestEntry(file_path=second_path, group="naive", subject="Mouse B"),
        ],
        SessionProfile.default(),
        GroupedPLVParams(phase_bins=18, align_preferred_phase=False, min_spikes_per_unit=1),
    )

    figure = create_publication_figure(result.preview_result)
    renderer = _draw_renderer(figure)
    axis = figure.axes[0]

    assert axis.get_legend() is not None
    assert not axis.get_legend().get_window_extent(renderer).overlaps(axis.get_window_extent(renderer))


def test_grouped_plv_composite_preview_keeps_legends_outside_each_polar_axis() -> None:
    first_path = Path("ca1_trained.nex5")
    second_path = Path("ca1_naive.nex5")
    third_path = Path("ec_trained.nex5")
    fourth_path = Path("ec_naive.nex5")
    sessions = {
        first_path: _make_grouped_plv_session("ca1_trained.nex5", unit_phase_offsets_deg=[0.0], region="CA1"),
        second_path: _make_grouped_plv_session("ca1_naive.nex5", unit_phase_offsets_deg=[90.0], region="CA1"),
        third_path: _make_grouped_plv_session("ec_trained.nex5", unit_phase_offsets_deg=[20.0], region="EC"),
        fourth_path: _make_grouped_plv_session("ec_naive.nex5", unit_phase_offsets_deg=[120.0], region="EC"),
    }
    runner = GroupedPLVRunner(loader=FakeLoader(sessions))
    result = runner.run_entries(
        [
            GroupedPLVManifestEntry(file_path=first_path, group="trained", subject="Mouse A", region="CA1"),
            GroupedPLVManifestEntry(file_path=second_path, group="naive", subject="Mouse B", region="CA1"),
            GroupedPLVManifestEntry(file_path=third_path, group="trained", subject="Mouse C", region="EC"),
            GroupedPLVManifestEntry(file_path=fourth_path, group="naive", subject="Mouse D", region="EC"),
        ],
        SessionProfile.default(),
        GroupedPLVParams(phase_bins=18, align_preferred_phase=False, min_spikes_per_unit=1, same_region_only=False),
    )

    figure = create_publication_figure(result.preview_result)
    renderer = _draw_renderer(figure)

    for axis in figure.axes:
        assert axis.name == "polar"
        assert axis.get_legend() is not None
        assert not axis.get_legend().get_window_extent(renderer).overlaps(axis.get_window_extent(renderer))


def test_grouped_plv_runner_exports_expected_tables(tmp_path: Path) -> None:
    session_path = Path("export_a.nex5")
    sessions = {
        session_path: _make_grouped_plv_session("export_a.nex5", unit_phase_offsets_deg=[0.0, 10.0]),
    }
    runner = GroupedPLVRunner(loader=FakeLoader(sessions))
    result = runner.run_entries(
        [
            GroupedPLVManifestEntry(file_path=session_path, group="trained", subject="Mouse A"),
        ],
        SessionProfile.default(),
        GroupedPLVParams(phase_bins=18, align_preferred_phase=True, min_spikes_per_unit=1),
    )

    exported = runner.export_run(result, tmp_path)

    assert exported["figure"].exists()
    assert exported["unit_level"].exists()
    assert exported["subject_level"].exists()
    assert exported["group_level"].exists()
