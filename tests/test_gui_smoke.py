from pathlib import Path

import pandas as pd

from nex5_analyzer.analysis.service import AnalysisService
from nex5_analyzer.analysis.batch import BatchProgressUpdate, BatchRunReport
from nex5_analyzer.analysis.tree import AnalysisTreeBuilder
from nex5_analyzer.config import SessionProfile
from nex5_analyzer.gui.analysis_dialog import AnalysisWorkspaceDialog, ExportAllOutcome
from nex5_analyzer.gui.main_window import MainWindow
from nex5_analyzer.gui.preview import PreviewWidget
from nex5_analyzer.io.nex5_loader import Nex5SessionLoader
from nex5_analyzer.models import AnalysisResult
from nex5_analyzer.testing import make_synthetic_session, make_waveform_population_session


def test_main_window_smoke(tmp_path: Path, qapp) -> None:
    window = MainWindow(autosave_profile_path=tmp_path / "main_window_smoke.json")
    assert window.windowTitle()
    window.close()


def test_analysis_workspace_smoke(qapp) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)
    root = AnalysisTreeBuilder().build(session, profile)

    assert dialog.windowTitle()
    assert root.children
    dialog.close()


def test_analysis_workspace_tree_is_collapsed_by_default(qapp) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)

    assert dialog.tree.topLevelItemCount() > 0
    assert all(not dialog.tree.topLevelItem(index).isExpanded() for index in range(dialog.tree.topLevelItemCount()))
    dialog.close()


def test_analysis_workspace_opens_with_readable_default_splitter_sizes(qapp) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)
    dialog.show()
    qapp.processEvents()

    sizes = dialog.content_splitter.sizes()

    assert len(sizes) == 3
    assert sizes[0] >= 260
    assert sizes[1] >= 700
    assert sizes[2] >= 300
    assert sizes[1] > sizes[0]
    assert sizes[1] > sizes[2]
    dialog.close()


def test_analysis_workspace_supports_maximize_toggle(qapp) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)
    dialog.show()
    qapp.processEvents()

    assert dialog.maximize_button.text() == "最大化"
    assert bool(dialog.windowFlags() & dialog.windowFlags().__class__.WindowMaximizeButtonHint)

    dialog._toggle_maximized()
    qapp.processEvents()

    assert dialog.isMaximized() is True
    assert dialog.maximize_button.text() == "还原"

    dialog._toggle_maximized()
    qapp.processEvents()

    assert dialog.isMaximized() is False
    assert dialog.maximize_button.text() == "最大化"
    dialog.close()


def test_preview_widget_switches_between_heatmap_and_line_without_layout_crash(qapp) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    service = AnalysisService()
    root = AnalysisTreeBuilder().build(session, profile)
    preview = PreviewWidget()

    heatmap = service.compute(session, root.find_node("lfp:spectrogram:ch01"), profile, {})
    line = service.compute(session, root.find_node("lfp:psd:ch01"), profile, {})

    preview.render(heatmap)
    preview.render(line)
    preview.render(heatmap)

    assert len(preview.canvas.figure.axes) == 2
    preview.close()


def test_preview_widget_switches_between_heatmap_polar_and_line_without_layout_crash(qapp) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    service = AnalysisService()
    root = AnalysisTreeBuilder().build(session, profile)
    preview = PreviewWidget()

    heatmap = service.compute(session, root.find_node("lfp:spectrogram:ch01"), profile, {})
    polar = service.compute(session, root.find_node("lfp:pac_polar:ch01"), profile, {})
    line = service.compute(session, root.find_node("lfp:psd:ch01"), profile, {})

    preview.render(heatmap)
    preview.render(polar)
    preview.render(line)
    preview.render(polar)

    assert preview.canvas.figure.axes[0].name == "polar"
    preview.close()


def test_preview_widget_switches_between_scatter3d_and_line_without_layout_crash(qapp) -> None:
    session = make_waveform_population_session()
    profile = SessionProfile.default()
    service = AnalysisService()
    root = AnalysisTreeBuilder().build(session, profile)
    preview = PreviewWidget()

    scatter3d = service.compute(session, root.find_node("spike:waveform_characterization:summary"), profile, {})
    line = service.compute(session, root.find_node("spike:waveform_characterization:unit_ch01_u01"), profile, {})

    preview.render(scatter3d)
    preview.render(line)
    preview.render(scatter3d)

    assert preview.canvas.figure.axes[0].name == "3d"
    preview.close()


def test_parameter_panel_handles_partial_values_without_crashing(qapp) -> None:
    from nex5_analyzer.gui.parameter_panel import ParameterPanel

    panel = ParameterPanel()
    panel.set_analysis("pac", {"phase_min_hz": 4.0})

    values = panel.values()

    assert values["phase_min_hz"] == 4.0
    assert values["phase_max_hz"] == 0.1
    assert values["amp_max_hz"] == 0.1
    panel.close()


def test_parameter_panel_supports_choice_parameters_and_toggle_dependencies(qapp) -> None:
    from nex5_analyzer.gui.parameter_panel import ParameterPanel

    panel = ParameterPanel()
    panel.set_analysis(
        "psd",
        {
            "window_function": "hamming",
            "welch_average": "median",
            "plot_use_custom_x_range": False,
        },
    )

    values = panel.values()

    assert values["window_function"] == "hamming"
    assert values["welch_average"] == "median"
    assert panel._widgets["plot_x_min"].isEnabled() is False

    panel._widgets["plot_use_custom_x_range"].setChecked(True)
    assert panel._widgets["plot_x_min"].isEnabled() is True
    panel.close()


def test_analysis_workspace_ignores_stale_results(qapp) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)
    rendered: list[str] = []
    dialog.preview.render = lambda result: rendered.append(result.title)
    dialog._latest_request_id = 2

    stale = AnalysisResult(node_id="a", title="stale", kind="message", message="old")
    fresh = AnalysisResult(node_id="b", title="fresh", kind="message", message="new")

    dialog._on_result_ready(1, stale)
    assert rendered == []

    dialog._on_result_ready(2, fresh)
    assert rendered == ["fresh"]
    assert dialog.current_result == fresh
    dialog.close()


def test_analysis_workspace_uses_export_defaults_for_save_suggestions(qapp) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    profile.export_defaults["figure_formats"] = ["svg", "png"]
    profile.export_defaults["data_format"] = "csv"
    dialog = AnalysisWorkspaceDialog(session, profile)
    dialog.current_result = AnalysisResult(
        node_id="lfp:psd:ch01",
        title="PSD",
        kind="line",
        export_table=pd.DataFrame({"frequency_hz": [1.0], "power": [2.0]}),
    )

    assert dialog._default_figure_export_path().suffix == ".svg"
    assert dialog._default_data_export_path().suffix == ".csv"
    dialog.close()


def test_analysis_workspace_default_export_stem_reflects_subject_name(qapp) -> None:
    session = make_synthetic_session().with_region_map({1: {"subject": "Alpha", "region": "M1"}})
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:psd:ch01")
    dialog.current_node = node
    dialog.current_result = AnalysisService().compute(session, node, profile, {})

    stem = dialog._default_export_stem()

    assert "alpha" in stem
    assert stem.startswith("lfp_psd_")
    dialog.close()


def test_analysis_workspace_distinguishes_current_and_all_export_actions(qapp) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)

    assert dialog.export_current_figure_button.isEnabled() is False
    assert dialog.export_current_data_button.isEnabled() is False
    assert dialog.export_all_figures_button.isEnabled() is True
    assert dialog.export_all_data_button.isEnabled() is True

    dialog.current_result = AnalysisResult(
        node_id="lfp:psd:ch01",
        title="PSD",
        kind="line",
        export_table=pd.DataFrame({"frequency_hz": [1.0], "power": [2.0]}),
    )
    dialog._refresh_export_buttons()

    assert dialog.export_current_figure_button.isEnabled() is True
    assert dialog.export_current_data_button.isEnabled() is True
    assert dialog.export_all_figures_button.isEnabled() is True
    assert dialog.export_all_data_button.isEnabled() is True
    dialog.close()


def test_analysis_workspace_export_progress_updates_status_and_progress_bar(qapp) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)

    dialog._on_export_all_progress(
        BatchProgressUpdate(
            phase="processing",
            total_files=1,
            completed_files=0,
            current_file=session.file_path,
            total_tasks=10,
            completed_tasks=4,
            current_task="lfp:psd:ch01",
            completed_chunks=1,
            total_chunks=3,
            message="Batch 2/3 in progress",
            eta_seconds=12.0,
        )
    )

    assert dialog.export_progress_bar.value() == 40
    status = dialog.export_status_view.toPlainText()
    assert "4 / 10" in status
    assert "lfp:psd:ch01" in status
    assert "12s" in status
    dialog.close()


def test_analysis_workspace_start_export_all_enables_progress_injection(monkeypatch, tmp_path: Path, qapp) -> None:
    import nex5_analyzer.gui.analysis_dialog as analysis_dialog_module

    class DummySignal:
        def __init__(self) -> None:
            self.callbacks: list = []

        def connect(self, callback) -> None:
            self.callbacks.append(callback)

    class DummySignals:
        def __init__(self) -> None:
            self.result = DummySignal()
            self.error = DummySignal()
            self.finished = DummySignal()
            self.progress = DummySignal()
            self.cancelled = DummySignal()

    recorded: dict[str, object] = {}

    class FakeTaskWorker:
        def __init__(self, callback, *args, inject_progress=False, cancellation_token=None, **kwargs) -> None:
            recorded["callback"] = callback
            recorded["inject_progress"] = inject_progress
            recorded["args"] = args
            recorded["kwargs"] = kwargs
            self.signals = DummySignals()

    class DummyPool:
        def start(self, worker) -> None:
            recorded["worker"] = worker

    session = make_synthetic_session()
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)
    dialog.export_thread_pool = DummyPool()
    monkeypatch.setattr(analysis_dialog_module, "TaskWorker", FakeTaskWorker)

    dialog._start_export_all(tmp_path, export_figures=False, export_data=True)

    assert recorded["inject_progress"] is True
    worker = recorded["worker"]
    assert len(worker.signals.progress.callbacks) == 1
    dialog.close()


def test_analysis_workspace_execute_export_all_forwards_progress_callback(monkeypatch, tmp_path: Path, qapp) -> None:
    import nex5_analyzer.gui.analysis_dialog as analysis_dialog_module

    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, service=None) -> None:
            captured["service"] = service

        def export_session(
            self,
            session,
            output_dir,
            profile,
            analysis_keys=None,
            export_figures=True,
            export_data=True,
            progress_callback=None,
            chunk_size=0,
            cancellation_token=None,
        ):
            captured["session"] = session
            captured["output_dir"] = output_dir
            captured["profile"] = profile
            captured["export_figures"] = export_figures
            captured["export_data"] = export_data
            captured["progress_callback"] = progress_callback
            captured["chunk_size"] = chunk_size
            return BatchRunReport(
                output_root=output_dir,
                run_summary_path=output_dir / "run_summary.csv",
                failures_path=output_dir / "failures.csv",
            )

    session = make_synthetic_session()
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)
    progress_updates: list[BatchProgressUpdate] = []
    monkeypatch.setattr(analysis_dialog_module, "BatchAnalysisRunner", FakeRunner)

    outcome = dialog._execute_export_all(
        tmp_path,
        export_figures=True,
        export_data=False,
        profile_snapshot=profile.clone(),
        progress_callback=progress_updates.append,
    )

    assert isinstance(outcome, ExportAllOutcome)
    assert captured["session"] == session
    assert captured["output_dir"] == tmp_path
    assert captured["export_figures"] is True
    assert captured["export_data"] is False
    captured["progress_callback"](
        BatchProgressUpdate(
            phase="finished",
            total_files=1,
            completed_files=1,
            total_tasks=1,
            completed_tasks=1,
        )
    )
    assert len(progress_updates) == 1
    dialog.close()


def test_main_window_apply_region_mapping_updates_session_and_enables_workspace(
    sample_nex5_path,
    tmp_path: Path,
    qapp,
) -> None:
    window = MainWindow(autosave_profile_path=tmp_path / "region_mapping_state.json")
    window.load_session(sample_nex5_path)
    channel_ids = window.session.channel_ids

    assert window.open_workspace_button.isEnabled() is False

    region_map = {channel_id: "M1" for channel_id in channel_ids}
    window._apply_region_map(region_map)

    assert window.profile.channel_region_map == region_map
    assert window.open_workspace_button.isEnabled() is True
    assert all(unit.region == "M1" for unit in window.session.spike_units if unit.channel_id in channel_ids)
    window.close()


def test_main_window_restores_region_mapping_from_autosave(sample_nex5_path, tmp_path: Path, qapp) -> None:
    autosave_path = tmp_path / "autosave_profile.json"

    first_window = MainWindow(autosave_profile_path=autosave_path)
    first_window.load_session(sample_nex5_path)
    region_map = {channel_id: f"M{channel_id}" for channel_id in first_window.session.channel_ids}

    first_window._apply_region_map(region_map)
    first_window.close()

    second_window = MainWindow(autosave_profile_path=autosave_path)
    second_window.load_session(sample_nex5_path)

    assert second_window.profile.channel_region_map == region_map
    assert second_window.open_workspace_button.isEnabled() is True
    assert autosave_path.exists() is True
    second_window.close()


def test_main_window_applies_subject_region_mapping(sample_nex5_path, tmp_path: Path, qapp) -> None:
    window = MainWindow(autosave_profile_path=tmp_path / "subject_mapping_state.json")
    window.load_session(sample_nex5_path)
    channel_ids = window.session.channel_ids

    region_map = {
        channel_id: {"subject": "Mouse A", "region": f"M{channel_id}"}
        for channel_id in channel_ids
    }
    window._apply_region_map(region_map)

    assert window.profile.channel_region_map == region_map
    assert all(unit.subject == "Mouse A" for unit in window.session.spike_units if unit.channel_id in channel_ids)
    assert window.mapping_table.columnCount() == 6
    window.close()


def test_analysis_workspace_apply_and_reset_round_trip(lfp_sample_nex5_path, qapp) -> None:
    session = Nex5SessionLoader().inspect(lfp_sample_nex5_path)
    profile = SessionProfile.default()
    dialog = AnalysisWorkspaceDialog(session, profile)
    node = AnalysisTreeBuilder().build(session, profile).find_node("lfp:psd:ch01")
    peer_node = AnalysisTreeBuilder().build(session, profile).find_node("lfp:psd:ch02")
    defaults = profile.resolved_params(node.analysis_key, node.node_id)
    baseline_default = SessionProfile.default().analysis_defaults["psd"]["max_freq_hz"]
    calls: list[tuple[dict, bool]] = []

    dialog.current_node = node
    dialog.parameter_panel.set_analysis(node.analysis_key, defaults)
    dialog._compute_current_node = lambda params, show_validation_dialog: calls.append((params, show_validation_dialog)) or True
    dialog.parameter_panel._widgets["max_freq_hz"].setValue(180.0)

    dialog._on_apply_clicked()
    assert profile.analysis_defaults["psd"]["max_freq_hz"] == 180.0
    assert calls[-1][0]["max_freq_hz"] == 180.0
    assert calls[-1][1] is True
    dialog.current_node = peer_node
    dialog.parameter_panel.set_analysis(peer_node.analysis_key, profile.resolved_params(peer_node.analysis_key, peer_node.node_id))
    assert dialog.parameter_panel.values()["max_freq_hz"] == 180.0

    dialog._on_reset_clicked()
    assert profile.analysis_defaults["psd"]["max_freq_hz"] == baseline_default
    assert dialog.parameter_panel.values()["max_freq_hz"] == baseline_default
    assert calls[-1][0]["max_freq_hz"] == baseline_default
    dialog.close()


def test_main_window_execute_batch_analysis_uses_current_profile(tmp_path: Path, qapp) -> None:
    window = MainWindow(autosave_profile_path=tmp_path / "batch_state.json")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    captured: dict = {}
    for checkbox in window.batch_analysis_checkboxes.values():
        checkbox.setChecked(False)
    window.batch_analysis_checkboxes["psd"].setChecked(True)
    window.batch_analysis_checkboxes["isi"].setChecked(True)

    def fake_run_directory(
        batch_input,
        batch_output,
        profile,
        analysis_keys=None,
        reference_channel_ids=None,
        progress_callback=None,
        cancellation_token=None,
    ):
        captured["input"] = batch_input
        captured["output"] = batch_output
        captured["profile"] = profile
        captured["analysis_keys"] = analysis_keys
        captured["reference_channel_ids"] = reference_channel_ids
        profile.analysis_defaults["psd"]["max_freq_hz"] = 999.0
        return BatchRunReport(
            output_root=batch_output,
            run_summary_path=batch_output / "run_summary.csv",
            failures_path=batch_output / "failures.csv",
        )

    window.batch_runner.run_directory = fake_run_directory

    report = window._execute_batch_run(input_dir, output_dir)

    assert captured["input"] == input_dir
    assert captured["output"] == output_dir
    assert captured["profile"] is not window.profile
    assert captured["analysis_keys"] == {"psd", "isi"}
    assert captured["reference_channel_ids"] is None
    assert report.output_root == output_dir
    assert captured["profile"].input_defaults["batch_input_dir"] == str(input_dir)
    assert captured["profile"].input_defaults["batch_output_dir"] == str(output_dir)
    assert captured["profile"].input_defaults["batch_analysis_keys"] == ["isi", "psd"]
    assert window.profile.input_defaults["batch_input_dir"] == ""
    assert window.profile.input_defaults["batch_output_dir"] == ""
    assert window.profile.analysis_defaults["psd"]["max_freq_hz"] != 999.0
    window.close()


def test_main_window_batch_selection_falls_back_when_saved_keys_are_stale(tmp_path: Path, qapp) -> None:
    window = MainWindow(autosave_profile_path=tmp_path / "batch_stale_keys_state.json")
    for checkbox in window.batch_analysis_checkboxes.values():
        checkbox.setChecked(False)
    window.profile.input_defaults["batch_analysis_keys"] = ["fft"]

    window._apply_batch_analysis_selection_from_profile()

    assert window._selected_batch_analysis_keys()
    assert "psd" in window._selected_batch_analysis_keys()
    window.close()


def test_main_window_batch_completion_updates_status(tmp_path: Path, qapp) -> None:
    window = MainWindow(autosave_profile_path=tmp_path / "batch_completion_state.json")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    report = BatchRunReport(
        output_root=output_dir,
        run_summary_path=output_dir / "run_summary.csv",
        failures_path=output_dir / "failures.csv",
    )
    report.outputs.extend([object(), object()])
    report.failures.append(object())
    window.batch_run_button.setEnabled(False)

    window._on_batch_run_success(report)

    status = window.batch_status_view.toPlainText()
    assert str(report.run_summary_path) in status
    assert str(report.failures_path) in status
    assert window.batch_progress_bar.value() == 100
    assert window.batch_run_button.isEnabled() is True
    window.close()


def test_main_window_batch_progress_updates_status_and_progress_bar(tmp_path: Path, qapp) -> None:
    window = MainWindow(autosave_profile_path=tmp_path / "batch_progress_state.json")

    window._on_batch_progress(
        BatchProgressUpdate(
            phase="loading",
            total_files=4,
            completed_files=1,
            current_file=Path("sample_b.nex5"),
            success_count=1,
            failure_count=0,
            message="loading sample_b.nex5",
        )
    )

    assert window.batch_progress_bar.value() == 25
    assert "sample_b.nex5" in window.batch_status_view.toPlainText()

    window._on_batch_progress(
        BatchProgressUpdate(
            phase="finished",
            total_files=4,
            completed_files=4,
            success_count=3,
            failure_count=1,
            message="finished",
        )
    )

    assert window.batch_progress_bar.value() == 100
    assert "4 / 4" in window.batch_status_view.toPlainText()
    window.close()
