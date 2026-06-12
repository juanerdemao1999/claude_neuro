from __future__ import annotations

import csv
import gc
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..config import SessionProfile
from ..export_naming import build_analysis_output_stem
from ..exporters import export_result_data, export_result_figure
from ..cancellation import CancellationToken, CancelledError
from ..io.nex5_loader import Nex5SessionLoader
from ..models import AnalysisNode, AnalysisResult, SessionData, normalize_region_assignment
from .service import AnalysisService
from .tree import AnalysisTreeBuilder


@dataclass(frozen=True, slots=True)
class BatchAnalysisTask:
    session_file: Path
    node_id: str
    analysis_key: str
    output_stem: str


@dataclass(slots=True)
class BatchAnalysisOutput:
    task: BatchAnalysisTask
    result: AnalysisResult | None
    figure_paths: dict[str, Path] = field(default_factory=dict)
    data_path: Path | None = None


@dataclass(frozen=True, slots=True)
class BatchTaskFailure:
    session_file: Path
    analysis_key: str
    node_id: str
    error_message: str


@dataclass(slots=True)
class BatchSessionExecution:
    outputs: list[BatchAnalysisOutput] = field(default_factory=list)
    failures: list[BatchTaskFailure] = field(default_factory=list)


@dataclass(slots=True)
class BatchRunReport:
    output_root: Path
    run_summary_path: Path
    failures_path: Path
    outputs: list[BatchAnalysisOutput] = field(default_factory=list)
    failures: list[BatchTaskFailure] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.outputs)

    @property
    def failure_count(self) -> int:
        return len(self.failures)


@dataclass(frozen=True, slots=True)
class BatchProgressUpdate:
    phase: str
    total_files: int
    completed_files: int
    current_file: Path | None = None
    success_count: int = 0
    failure_count: int = 0
    message: str = ""
    total_tasks: int = 0
    completed_tasks: int = 0
    current_task: str | None = None
    total_chunks: int = 0
    completed_chunks: int = 0
    elapsed_seconds: float = 0.0
    eta_seconds: float | None = None

    @property
    def progress_percent(self) -> int:
        if self.total_tasks > 0:
            if self.completed_tasks <= 0:
                return 0
            return int((self.completed_tasks / self.total_tasks) * 100)
        if self.total_files <= 0:
            return 0
        return int((self.completed_files / self.total_files) * 100)


class BatchAnalysisRunner:
    def __init__(self, service: AnalysisService | None = None, loader: Any | None = None) -> None:
        self.service = service or AnalysisService()
        self.loader = loader or Nex5SessionLoader()

    def build_tasks(
        self,
        session: SessionData,
        profile: SessionProfile,
        analysis_keys: set[str] | None = None,
    ) -> list[BatchAnalysisTask]:
        root = AnalysisTreeBuilder().build(session, profile)
        leaf_nodes = list(_iter_leaf_nodes(root))
        return self._build_tasks_for_leaf_nodes(session, leaf_nodes, analysis_keys)

    def execute_session(
        self,
        session: SessionData,
        profile: SessionProfile,
        analysis_keys: set[str] | None = None,
    ) -> BatchSessionExecution:
        root = AnalysisTreeBuilder().build(session, profile)
        leaf_nodes = list(_iter_leaf_nodes(root))
        node_lookup = {node.node_id: node for node in leaf_nodes}
        execution = BatchSessionExecution()
        for task in self._build_tasks_for_leaf_nodes(session, leaf_nodes, analysis_keys):
            try:
                result = self.service.compute(session, node_lookup[task.node_id], profile, {})
            except Exception as exc:
                execution.failures.append(
                    BatchTaskFailure(
                        session_file=task.session_file,
                        analysis_key=task.analysis_key,
                        node_id=task.node_id,
                        error_message=str(exc),
                    )
                )
                continue
            execution.outputs.append(BatchAnalysisOutput(task=task, result=result))
        return execution

    def _build_tasks_for_leaf_nodes(
        self,
        session: SessionData,
        leaf_nodes: list[AnalysisNode],
        analysis_keys: set[str] | None = None,
        filename_template: str | None = None,
    ) -> list[BatchAnalysisTask]:
        tasks: list[BatchAnalysisTask] = []
        for node in leaf_nodes:
            if node.analysis_key is None:
                continue
            if analysis_keys is not None and node.analysis_key not in analysis_keys:
                continue
            tasks.append(
                BatchAnalysisTask(
                    session_file=session.file_path,
                    node_id=node.node_id,
                    analysis_key=node.analysis_key,
                    output_stem=build_analysis_output_stem(session, node, template=filename_template),
                )
            )
        return tasks

    def run_session(
        self,
        session: SessionData,
        profile: SessionProfile,
        analysis_keys: set[str] | None = None,
    ) -> list[BatchAnalysisOutput]:
        return self.execute_session(session, profile, analysis_keys=analysis_keys).outputs

    def export_session(
        self,
        session: SessionData,
        output_dir: Path,
        profile: SessionProfile,
        analysis_keys: set[str] | None = None,
        export_figures: bool = True,
        export_data: bool = True,
        progress_callback: Callable[[BatchProgressUpdate], None] | None = None,
        chunk_size: int = 24,
        cancellation_token: CancellationToken | None = None,
    ) -> BatchRunReport:
        if not export_figures and not export_data:
            raise ValueError("At least one export target must be enabled.")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report = BatchRunReport(
            output_root=output_dir,
            run_summary_path=output_dir / _summary_file_name(export_figures, export_data),
            failures_path=output_dir / _failures_file_name(export_figures, export_data),
        )
        root = AnalysisTreeBuilder().build(session, profile)
        leaf_nodes = list(_iter_leaf_nodes(root))
        node_lookup = {node.node_id: node for node in leaf_nodes}
        filename_template = profile.export_defaults.get("filename_template") or None
        tasks = self._build_tasks_for_leaf_nodes(session, leaf_nodes, analysis_keys, filename_template=filename_template)
        chunk_size = max(1, int(chunk_size))
        total_tasks = len(tasks)
        total_chunks = math.ceil(total_tasks / chunk_size) if total_tasks else 0
        completed_tasks = 0
        started_at = time.perf_counter()

        self.service.clear_result_cache()
        _emit_progress(
            progress_callback,
            BatchProgressUpdate(
                phase="starting",
                total_files=1,
                completed_files=0,
                current_file=session.file_path,
                total_tasks=total_tasks,
                completed_tasks=0,
                total_chunks=total_chunks,
                completed_chunks=0,
                success_count=report.success_count,
                failure_count=report.failure_count,
                message=f"Discovered {total_tasks} export tasks for {session.file_name}.",
            ),
        )

        if not tasks:
            report.failures.append(
                BatchTaskFailure(
                    session_file=session.file_path,
                    analysis_key="",
                    node_id="",
                    error_message="No selected analyses were applicable to this file.",
                )
            )
            self._write_run_summary(report)
            self._write_failures(report)
            _emit_progress(
                progress_callback,
                BatchProgressUpdate(
                    phase="finished",
                    total_files=1,
                    completed_files=1,
                    current_file=session.file_path,
                    total_tasks=0,
                    completed_tasks=0,
                    total_chunks=0,
                    completed_chunks=0,
                    success_count=report.success_count,
                    failure_count=report.failure_count,
                    message="No selected analyses were applicable to this file.",
                    elapsed_seconds=0.0,
                    eta_seconds=0.0,
                ),
            )
            return report

        for task in tasks:
            if cancellation_token is not None:
                cancellation_token.check()
            current_chunk = (completed_tasks // chunk_size) + 1
            chunk_start = ((current_chunk - 1) * chunk_size) + 1
            chunk_end = min(total_tasks, current_chunk * chunk_size)
            elapsed_seconds, eta_seconds = _timing_progress(started_at, completed_tasks, total_tasks)
            _emit_progress(
                progress_callback,
                BatchProgressUpdate(
                    phase="processing",
                    total_files=1,
                    completed_files=0,
                    current_file=session.file_path,
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    current_task=task.node_id,
                    total_chunks=total_chunks,
                    completed_chunks=max(0, current_chunk - 1),
                    success_count=report.success_count,
                    failure_count=report.failure_count,
                    message=(
                        f"Batch {current_chunk}/{total_chunks} | "
                        f"tasks {chunk_start}-{chunk_end} | "
                        f"running {completed_tasks + 1} / {total_tasks}: {task.node_id}"
                    ),
                    elapsed_seconds=elapsed_seconds,
                    eta_seconds=eta_seconds,
                ),
            )

            output: BatchAnalysisOutput | None = None
            try:
                result = self.service.compute(
                    session,
                    node_lookup[task.node_id],
                    profile,
                    {},
                    cache_result=False,
                )
                output = BatchAnalysisOutput(task=task, result=result)
                self._export_output(
                    output_dir,
                    profile,
                    output,
                    export_figures=export_figures,
                    export_data=export_data,
                )
                output.result = None
                report.outputs.append(output)
            except Exception as exc:
                report.failures.append(
                    BatchTaskFailure(
                        session_file=task.session_file,
                        analysis_key=task.analysis_key,
                        node_id=task.node_id,
                        error_message=str(exc),
                    )
                )
            finally:
                if output is not None:
                    output.result = None
                self.service.clear_result_cache()
                self.service.clear_runtime_cache()
                _release_session_data_cache(session)
                gc.collect()

            completed_tasks += 1
            if completed_tasks % chunk_size == 0 or completed_tasks == total_tasks:
                self.service.clear_result_cache()
                self.service.clear_runtime_cache()
                _release_session_data_cache(session)
                gc.collect()

        self._write_run_summary(report)
        self._write_failures(report)
        elapsed_seconds, eta_seconds = _timing_progress(started_at, completed_tasks, total_tasks)
        _emit_progress(
            progress_callback,
            BatchProgressUpdate(
                phase="finished",
                total_files=1,
                completed_files=1,
                current_file=session.file_path,
                total_tasks=total_tasks,
                completed_tasks=completed_tasks,
                total_chunks=total_chunks,
                completed_chunks=total_chunks,
                success_count=report.success_count,
                failure_count=report.failure_count,
                message=f"Finished exporting {session.file_name}.",
                elapsed_seconds=elapsed_seconds,
                eta_seconds=eta_seconds,
            ),
        )
        return report

    def run_directory(
        self,
        input_dir: Path,
        output_dir: Path,
        profile: SessionProfile,
        analysis_keys: set[str] | None = None,
        reference_channel_ids: list[int] | None = None,
        progress_callback: Callable[[BatchProgressUpdate], None] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> BatchRunReport:
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(input_dir.glob("*.nex5"))
        report = BatchRunReport(
            output_root=output_dir,
            run_summary_path=output_dir / "run_summary.csv",
            failures_path=output_dir / "failures.csv",
        )
        _emit_progress(
            progress_callback,
            BatchProgressUpdate(
                phase="starting",
                total_files=len(files),
                completed_files=0,
                message=f"Discovered {len(files)} NEX5 files.",
            ),
        )

        for index, file_path in enumerate(files, start=1):
            if cancellation_token is not None:
                cancellation_token.check()
            _emit_progress(
                progress_callback,
                BatchProgressUpdate(
                    phase="loading",
                    total_files=len(files),
                    completed_files=index - 1,
                    current_file=file_path,
                    success_count=report.success_count,
                    failure_count=report.failure_count,
                    message=f"Processing {file_path.name}",
                ),
            )
            try:
                session = self.loader.inspect(
                    file_path,
                    manual_channel_ids=profile.input_defaults.get("manual_channel_ids", {}),
                    region_map=profile.channel_region_map,
                )
            except Exception as exc:
                report.failures.append(
                    BatchTaskFailure(
                        session_file=file_path,
                        analysis_key="",
                        node_id="",
                        error_message=str(exc),
                    )
                )
                _emit_progress(
                    progress_callback,
                    BatchProgressUpdate(
                        phase="completed",
                        total_files=len(files),
                        completed_files=index,
                        current_file=file_path,
                        success_count=report.success_count,
                        failure_count=report.failure_count,
                        message=f"Failed to load {file_path.name}",
                    ),
                )
                continue

            validation_error = _validate_batch_session(
                session,
                profile,
                reference_channel_ids=reference_channel_ids,
            )
            if validation_error is not None:
                report.failures.append(
                    BatchTaskFailure(
                        session_file=file_path,
                        analysis_key="",
                        node_id="",
                        error_message=validation_error,
                    )
                )
                _emit_progress(
                    progress_callback,
                    BatchProgressUpdate(
                        phase="completed",
                        total_files=len(files),
                        completed_files=index,
                        current_file=file_path,
                        success_count=report.success_count,
                        failure_count=report.failure_count,
                        message=f"Skipped {file_path.name}: {validation_error}",
                    ),
                )
                continue

            root = AnalysisTreeBuilder().build(session, profile)
            leaf_nodes = list(_iter_leaf_nodes(root))
            node_lookup = {node.node_id: node for node in leaf_nodes}
            filename_template = profile.export_defaults.get("filename_template") or None
            tasks = self._build_tasks_for_leaf_nodes(session, leaf_nodes, analysis_keys, filename_template=filename_template)
            if not tasks:
                report.failures.append(
                    BatchTaskFailure(
                        session_file=file_path,
                        analysis_key="",
                        node_id="",
                        error_message="No selected analyses were applicable to this file.",
                    )
                )
                _emit_progress(
                    progress_callback,
                    BatchProgressUpdate(
                        phase="completed",
                        total_files=len(files),
                        completed_files=index,
                        current_file=file_path,
                        success_count=report.success_count,
                        failure_count=report.failure_count,
                        message=f"Skipped {file_path.name}: no applicable analyses.",
                    ),
                )
                continue

            self.service.clear_result_cache()
            self.service.clear_runtime_cache()
            _release_session_data_cache(session)
            for task in tasks:
                output: BatchAnalysisOutput | None = None
                try:
                    result = self.service.compute(
                        session,
                        node_lookup[task.node_id],
                        profile,
                        {},
                        cache_result=False,
                    )
                    output = BatchAnalysisOutput(task=task, result=result)
                    self._export_output(output_dir, profile, output)
                except Exception as exc:
                    report.failures.append(
                        BatchTaskFailure(
                            session_file=task.session_file,
                            analysis_key=task.analysis_key,
                            node_id=task.node_id,
                            error_message=str(exc),
                        )
                    )
                    continue
                finally:
                    if output is not None:
                        output.result = None
                    self.service.clear_result_cache()
                    self.service.clear_runtime_cache()
                    _release_session_data_cache(session)
                    gc.collect()
                report.outputs.append(output)
            _emit_progress(
                progress_callback,
                BatchProgressUpdate(
                    phase="completed",
                    total_files=len(files),
                    completed_files=index,
                    current_file=file_path,
                    success_count=report.success_count,
                    failure_count=report.failure_count,
                    message=f"Finished {file_path.name}",
                ),
            )

        self._write_run_summary(report)
        self._write_failures(report)
        _emit_progress(
            progress_callback,
            BatchProgressUpdate(
                phase="finished",
                total_files=len(files),
                completed_files=len(files),
                success_count=report.success_count,
                failure_count=report.failure_count,
                message="Batch analysis complete.",
            ),
        )
        return report

    def _export_output(
        self,
        output_root: Path,
        profile: SessionProfile,
        output: BatchAnalysisOutput,
        export_figures: bool = True,
        export_data: bool = True,
    ) -> None:
        if output.result is None:
            raise ValueError("Cannot export an empty analysis result.")
        file_root = output_root / output.task.session_file.stem
        figures_dir = file_root / "figures"
        data_dir = file_root / "data"
        if export_figures:
            figures_dir.mkdir(parents=True, exist_ok=True)
        if export_data:
            data_dir.mkdir(parents=True, exist_ok=True)

        if export_figures:
            for figure_format in _preferred_figure_formats(profile):
                figure_path = figures_dir / f"{output.task.output_stem}.{figure_format}"
                export_result_figure(output.result, figure_path)
                output.figure_paths[figure_format] = figure_path

        if export_data:
            data_path = data_dir / f"{output.task.output_stem}.{_preferred_data_format(profile)}"
            export_result_data(output.result, data_path)
            output.data_path = data_path

    def _write_run_summary(self, report: BatchRunReport) -> None:
        with report.run_summary_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["file_name", "analysis_key", "node_id", "figure_png", "figure_svg", "data_csv", "status"],
            )
            writer.writeheader()
            for output in report.outputs:
                writer.writerow(
                    {
                        "file_name": output.task.session_file.name,
                        "analysis_key": output.task.analysis_key,
                        "node_id": output.task.node_id,
                        "figure_png": _relative_or_blank(report.output_root, output.figure_paths.get("png")),
                        "figure_svg": _relative_or_blank(report.output_root, output.figure_paths.get("svg")),
                        "data_csv": _relative_or_blank(report.output_root, output.data_path),
                        "status": "success",
                    }
                )

    def _write_failures(self, report: BatchRunReport) -> None:
        with report.failures_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["file_name", "analysis_key", "node_id", "status", "error_message"],
            )
            writer.writeheader()
            for failure in report.failures:
                writer.writerow(
                    {
                        "file_name": failure.session_file.name,
                        "analysis_key": failure.analysis_key,
                        "node_id": failure.node_id,
                        "status": "failed",
                        "error_message": failure.error_message,
                    }
                )


def _iter_leaf_nodes(node: AnalysisNode):
    if not node.children:
        yield node
        return
    for child in node.children:
        yield from _iter_leaf_nodes(child)


def _validate_batch_session(
    session: SessionData,
    profile: SessionProfile,
    reference_channel_ids: list[int] | None = None,
) -> str | None:
    normalized_reference = sorted({int(channel_id) for channel_id in reference_channel_ids or []})
    session_channel_ids = sorted({int(channel_id) for channel_id in session.channel_ids})
    if normalized_reference and session_channel_ids != normalized_reference:
        return (
            "Logical channel layout "
            f"{session_channel_ids} does not match the current batch reference sample {normalized_reference}."
        )

    missing_region_channels = [
        channel_id
        for channel_id in session_channel_ids
        if normalize_region_assignment(profile.channel_region_map.get(channel_id)) is None
    ]
    if missing_region_channels:
        return (
            "Brain-region mapping is incomplete for logical channels: "
            + ", ".join(str(channel_id) for channel_id in missing_region_channels)
        )
    return None


def _release_session_data_cache(session: SessionData) -> None:
    clear_cache = getattr(getattr(session, "data_store", None), "clear_cache", None)
    if callable(clear_cache):
        clear_cache()


def _preferred_figure_formats(profile: SessionProfile) -> list[str]:
    formats: list[str] = []
    for raw_format in profile.export_defaults.get("figure_formats", []):
        normalized = str(raw_format).lower().lstrip(".")
        if normalized in {"png", "svg"} and normalized not in formats:
            formats.append(normalized)
    return formats or ["png"]


def _preferred_data_format(profile: SessionProfile) -> str:
    normalized = str(profile.export_defaults.get("data_format", "csv")).lower().lstrip(".")
    return normalized if normalized == "csv" else "csv"


def _relative_or_blank(output_root: Path, path: Path | None) -> str:
    if path is None:
        return ""
    return str(path.relative_to(output_root))


def _summary_file_name(export_figures: bool, export_data: bool) -> str:
    if export_figures and export_data:
        return "run_summary.csv"
    if export_figures:
        return "figure_exports.csv"
    return "data_exports.csv"


def _failures_file_name(export_figures: bool, export_data: bool) -> str:
    if export_figures and export_data:
        return "failures.csv"
    if export_figures:
        return "figure_export_failures.csv"
    return "data_export_failures.csv"


def _emit_progress(
    progress_callback: Callable[[BatchProgressUpdate], None] | None,
    update: BatchProgressUpdate,
) -> None:
    if _should_log_progress(update):
        print(_format_progress(update), flush=True)
    if progress_callback is not None:
        progress_callback(update)


def _timing_progress(started_at: float, completed: int, total: int) -> tuple[float, float | None]:
    elapsed_seconds = max(0.0, time.perf_counter() - started_at)
    if total <= 0 or completed <= 0:
        return elapsed_seconds, None
    remaining = max(0, total - completed)
    rate = elapsed_seconds / completed
    return elapsed_seconds, remaining * rate


def _should_log_progress(update: BatchProgressUpdate) -> bool:
    if update.total_tasks > 0:
        return update.phase in {"starting", "processing", "finished"}
    return True


def _format_progress(update: BatchProgressUpdate) -> str:
    parts = [f"[{update.phase}]"]
    if update.current_file is not None:
        parts.append(update.current_file.name)
    if update.total_tasks > 0:
        task_label = update.current_task or "-"
        parts.append(f"tasks {update.completed_tasks} / {update.total_tasks}")
        parts.append(f"current {task_label}")
        if update.total_chunks > 0:
            batch_index = update.total_chunks if update.phase == "finished" else min(
                update.completed_chunks + 1,
                update.total_chunks,
            )
            parts.append(f"batch {batch_index}/{update.total_chunks}")
        if update.eta_seconds is not None:
            parts.append(f"eta {_format_duration(update.eta_seconds)}")
    else:
        parts.append(f"files {update.completed_files} / {update.total_files}")
    parts.append(f"ok {update.success_count}")
    parts.append(f"fail {update.failure_count}")
    if update.message:
        parts.append(update.message)
    return " | ".join(parts)


def _format_duration(seconds: float) -> str:
    rounded = max(0, int(round(seconds)))
    minutes, remaining_seconds = divmod(rounded, 60)
    hours, remaining_minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {remaining_minutes}m"
    if minutes > 0:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"
