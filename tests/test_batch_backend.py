from dataclasses import replace
from pathlib import Path

from nex5_analyzer.analysis.batch import BatchAnalysisRunner, BatchProgressUpdate
from nex5_analyzer.analysis.registry import get_analysis_definition
from nex5_analyzer.analysis.tree import AnalysisTreeBuilder
from nex5_analyzer.config import SessionProfile
from nex5_analyzer.testing import make_synthetic_session


def test_registry_returns_expected_definition_metadata() -> None:
    definition = get_analysis_definition("psd")

    assert definition.key == "psd"
    assert definition.scope == "lfp"
    assert definition.build_mode == "lfp_each"
    assert definition.default_params["max_freq_hz"] == 120.0
    assert definition.default_params["nperseg"] == 1024
    assert definition.default_params["y_max_db"] == 0.0
    assert definition.default_params["window_function"] == "hann"
    assert definition.default_params["welch_average"] == "mean"
    assert any(spec.key == "max_freq_hz" for spec in definition.parameter_specs)
    assert any(spec.key == "window_function" and spec.kind == "choice" for spec in definition.parameter_specs)


def test_batch_runner_builds_tasks_for_selected_analyses_only() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()

    tasks = BatchAnalysisRunner().build_tasks(session, profile, analysis_keys={"psd", "firing_rate"})

    assert {task.analysis_key for task in tasks} == {"psd", "firing_rate"}
    assert {task.node_id for task in tasks} == {"lfp:psd:ch01", "spike:firing_rate:unit_ch01_u01"}


def test_batch_runner_executes_selected_analyses_without_gui_state() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()

    outputs = BatchAnalysisRunner().run_session(session, profile, analysis_keys={"psd", "isi"})

    assert {output.task.analysis_key for output in outputs} == {"psd", "isi"}
    assert all(not output.result.export_table.empty for output in outputs)


def test_tree_builder_and_registry_stay_in_sync_for_enabled_analysis_keys() -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)

    enabled_leaf_keys = {
        node.analysis_key
        for category in root.children
        for subcategory in category.children
        for node in ([subcategory] if not subcategory.children else subcategory.children)
        if node.analysis_key is not None
    }

    assert {"psd", "pac", "pac_polar", "firing_rate", "sta"}.issubset(enabled_leaf_keys)


def test_batch_runner_run_directory_writes_outputs_and_summary_files(tmp_path: Path) -> None:
    class FakeLoader:
        def inspect(self, file_path, manual_channel_ids=None, region_map=None):
            session = make_synthetic_session()
            return replace(session, file_path=Path(file_path))

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "a.nex5").write_text("", encoding="utf-8")
    (input_dir / "b.nex5").write_text("", encoding="utf-8")

    profile = SessionProfile.default()
    profile.export_defaults["figure_formats"] = ["png"]
    profile.channel_region_map = {1: "M1"}
    runner = BatchAnalysisRunner(loader=FakeLoader())

    report = runner.run_directory(input_dir, output_dir, profile, analysis_keys={"psd"})

    assert report.success_count == 2
    assert report.failure_count == 0
    assert report.run_summary_path.exists()
    assert report.failures_path.exists()
    assert (output_dir / "a" / "figures" / "lfp_psd_ch01.png").exists()
    assert (output_dir / "a" / "data" / "lfp_psd_ch01.csv").exists()
    assert "a.nex5" in report.run_summary_path.read_text(encoding="utf-8")


def test_batch_runner_run_directory_streams_each_task_before_next_compute(tmp_path: Path, monkeypatch) -> None:
    class FakeLoader:
        def inspect(self, file_path, manual_channel_ids=None, region_map=None):
            session = make_synthetic_session()
            return replace(session, file_path=Path(file_path))

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "large_lfp.nex5").write_text("", encoding="utf-8")

    profile = SessionProfile.default()
    profile.channel_region_map = {1: "M1"}
    runner = BatchAnalysisRunner(loader=FakeLoader())
    events: list[str] = []
    original_compute = runner.service.compute

    def recording_compute(session, node, profile, runtime_overrides=None, *, cache_result=True):
        events.append(f"compute:{node.node_id}")
        return original_compute(session, node, profile, runtime_overrides, cache_result=cache_result)

    def recording_export(output_root, profile, output, export_figures=True, export_data=True):
        events.append(f"export:{output.task.node_id}")

    monkeypatch.setattr(runner.service, "compute", recording_compute)
    monkeypatch.setattr(runner, "_export_output", recording_export)

    report = runner.run_directory(input_dir, output_dir, profile, analysis_keys={"psd", "spectrogram"})

    assert report.success_count == 2
    assert report.failure_count == 0
    assert events == [
        "compute:lfp:psd:ch01",
        "export:lfp:psd:ch01",
        "compute:lfp:spectrogram:ch01",
        "export:lfp:spectrogram:ch01",
    ]


def test_batch_runner_export_session_writes_all_data_without_figures(tmp_path: Path) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    profile.export_defaults["figure_formats"] = ["png"]
    runner = BatchAnalysisRunner()
    output_dir = tmp_path / "exports"

    report = runner.export_session(
        session,
        output_dir,
        profile,
        analysis_keys={"psd"},
        export_figures=False,
        export_data=True,
    )

    assert report.success_count == 1
    assert report.failure_count == 0
    assert report.run_summary_path.name == "data_exports.csv"
    assert report.failures_path.name == "data_export_failures.csv"
    assert (output_dir / session.file_path.stem / "data" / "lfp_psd_ch01.csv").exists()
    assert not (output_dir / session.file_path.stem / "figures").exists()


def test_batch_runner_export_session_includes_subject_name_in_output_file(tmp_path: Path) -> None:
    session = make_synthetic_session().with_region_map({1: {"subject": "Alpha", "region": "M1"}})
    profile = SessionProfile.default()
    profile.export_defaults["figure_formats"] = []
    runner = BatchAnalysisRunner()
    output_dir = tmp_path / "exports"

    report = runner.export_session(
        session,
        output_dir,
        profile,
        analysis_keys={"psd"},
        export_figures=False,
        export_data=True,
    )

    assert report.success_count == 1
    assert report.outputs[0].data_path is not None
    assert "alpha" in report.outputs[0].data_path.name.lower()


def test_batch_runner_export_session_writes_all_figures_without_data(tmp_path: Path) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    profile.export_defaults["figure_formats"] = ["png"]
    runner = BatchAnalysisRunner()
    output_dir = tmp_path / "exports"

    report = runner.export_session(
        session,
        output_dir,
        profile,
        analysis_keys={"psd"},
        export_figures=True,
        export_data=False,
    )

    assert report.success_count == 1
    assert report.failure_count == 0
    assert report.run_summary_path.name == "figure_exports.csv"
    assert report.failures_path.name == "figure_export_failures.csv"
    assert (output_dir / session.file_path.stem / "figures" / "lfp_psd_ch01.png").exists()
    assert not (output_dir / session.file_path.stem / "data").exists()


def test_batch_runner_export_session_streams_results_and_emits_task_progress(tmp_path: Path, capsys) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    profile.export_defaults["figure_formats"] = []
    runner = BatchAnalysisRunner()
    output_dir = tmp_path / "exports"
    events: list[BatchProgressUpdate] = []

    report = runner.export_session(
        session,
        output_dir,
        profile,
        analysis_keys={"psd", "spectrogram"},
        export_figures=False,
        export_data=True,
        progress_callback=events.append,
        chunk_size=1,
    )

    assert report.success_count == 2
    assert report.failure_count == 0
    assert len(runner.service._cache) == 0
    assert len(runner.service._shared_cache) == 0
    assert all(output.result is None for output in report.outputs)
    assert events[0].phase == "starting"
    assert events[-1].phase == "finished"
    assert events[-1].total_tasks == 2
    assert events[-1].completed_tasks == 2
    assert events[-1].progress_percent == 100
    assert any(event.current_task == "lfp:psd:ch01" for event in events)
    assert any("batch 1/2" in event.message.lower() for event in events)
    assert "2 / 2" in capsys.readouterr().out


def test_batch_runner_records_failures_without_aborting_remaining_files(tmp_path: Path) -> None:
    class MixedLoader:
        def inspect(self, file_path, manual_channel_ids=None, region_map=None):
            file_path = Path(file_path)
            if file_path.name == "bad.nex5":
                raise ValueError("broken sample")
            session = make_synthetic_session()
            return replace(session, file_path=file_path)

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "good.nex5").write_text("", encoding="utf-8")
    (input_dir / "bad.nex5").write_text("", encoding="utf-8")

    profile = SessionProfile.default()
    profile.export_defaults["figure_formats"] = []
    profile.channel_region_map = {1: "M1"}
    runner = BatchAnalysisRunner(loader=MixedLoader())

    report = runner.run_directory(input_dir, output_dir, profile, analysis_keys={"psd"})

    assert report.success_count == 1
    assert report.failure_count == 1
    assert "bad.nex5" in report.failures_path.read_text(encoding="utf-8")
    assert (output_dir / "good" / "data" / "lfp_psd_ch01.csv").exists()


def test_batch_runner_run_directory_emits_progress_updates(tmp_path: Path) -> None:
    class FakeLoader:
        def inspect(self, file_path, manual_channel_ids=None, region_map=None):
            session = make_synthetic_session()
            return replace(session, file_path=Path(file_path))

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "a.nex5").write_text("", encoding="utf-8")
    (input_dir / "b.nex5").write_text("", encoding="utf-8")

    profile = SessionProfile.default()
    profile.export_defaults["figure_formats"] = []
    profile.channel_region_map = {1: "M1"}
    runner = BatchAnalysisRunner(loader=FakeLoader())
    events: list[BatchProgressUpdate] = []

    report = runner.run_directory(input_dir, output_dir, profile, analysis_keys={"psd"}, progress_callback=events.append)

    assert report.success_count == 2
    assert [event.phase for event in events] == [
        "starting",
        "loading",
        "completed",
        "loading",
        "completed",
        "finished",
    ]
    assert events[0].total_files == 2
    assert events[1].current_file.name == "a.nex5"
    assert events[-1].completed_files == 2
    assert events[-1].success_count == 2


def test_batch_runner_marks_files_without_applicable_selected_analyses_as_failures(tmp_path: Path) -> None:
    class SpikeOnlyLoader:
        def inspect(self, file_path, manual_channel_ids=None, region_map=None):
            session = make_synthetic_session()
            spike_only = replace(
                session,
                file_path=Path(file_path),
                lfp_channels=[],
                region_map={1: "M1"},
            )
            return replace(spike_only, data_store=session.data_store)

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "spike_only.nex5").write_text("", encoding="utf-8")

    profile = SessionProfile.default()
    profile.export_defaults["figure_formats"] = []
    profile.channel_region_map = {1: "M1"}
    runner = BatchAnalysisRunner(loader=SpikeOnlyLoader())

    report = runner.run_directory(input_dir, output_dir, profile, analysis_keys={"psd"})

    assert report.success_count == 0
    assert report.failure_count == 1
    assert report.failures[0].error_message == "No selected analyses were applicable to this file."
    assert "spike_only.nex5" in report.failures_path.read_text(encoding="utf-8")


def test_batch_runner_rejects_files_with_channel_layout_mismatch_against_reference_sample(tmp_path: Path) -> None:
    class MismatchedLayoutLoader:
        def inspect(self, file_path, manual_channel_ids=None, region_map=None):
            session = make_synthetic_session()
            shifted_lfp = [replace(channel, channel_id=2, region=None) for channel in session.lfp_channels]
            shifted_units = [replace(unit, channel_id=2, region=None) for unit in session.spike_units]
            return replace(
                session,
                file_path=Path(file_path),
                lfp_channels=shifted_lfp,
                spike_units=shifted_units,
                region_map={},
            )

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "shifted.nex5").write_text("", encoding="utf-8")

    profile = SessionProfile.default()
    profile.export_defaults["figure_formats"] = []
    runner = BatchAnalysisRunner(loader=MismatchedLayoutLoader())

    report = runner.run_directory(
        input_dir,
        output_dir,
        profile,
        analysis_keys={"psd"},
        reference_channel_ids=[1],
    )

    assert report.success_count == 0
    assert report.failure_count == 1
    assert "does not match the current batch reference sample" in report.failures[0].error_message
