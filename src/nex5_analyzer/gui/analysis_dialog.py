from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..analysis.batch import BatchAnalysisRunner, BatchProgressUpdate, BatchRunReport
from ..analysis.registry import get_analysis_definition
from ..analysis.service import AnalysisService
from ..analysis.tree import AnalysisTreeBuilder
from ..analysis.validation import validate_analysis_request
from ..config import SessionProfile
from ..error_messages import friendly_error_message
from ..export_naming import build_analysis_output_stem, slugify_export_token
from ..exporters import export_result_data, export_result_figure
from ..models import AnalysisNode, AnalysisResult, SessionData
from .parameter_panel import ParameterPanel
from .preview import PreviewWidget
from .theme import ensure_app_theme, set_status_tone
from .workers import AnalysisWorker, CancellationToken, TaskWorker


@dataclass(slots=True)
class ExportAllOutcome:
    report: BatchRunReport
    service: AnalysisService


class AnalysisWorkspaceDialog(QDialog):
    def __init__(self, session: SessionData, profile: SessionProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        ensure_app_theme()
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)

        self.navigation_group: QGroupBox | None = None
        self.preview_group: QGroupBox | None = None
        self.parameter_group: QGroupBox | None = None
        self.content_splitter: QSplitter | None = None
        self.export_progress_bar: QProgressBar | None = None
        self.export_status_view: QTextEdit | None = None
        self.maximize_button: QPushButton | None = None

        self.session = session
        self.profile = profile
        self.service = AnalysisService()
        self.tree_root = AnalysisTreeBuilder().build(session, profile)
        self.current_node: AnalysisNode | None = None
        self.current_result: AnalysisResult | None = None
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(1)
        self.export_thread_pool = QThreadPool(self)
        self.export_thread_pool.setMaxThreadCount(1)
        self._export_busy = False
        self._latest_request_id = 0

        self.setWindowTitle("分析工作台")
        self.resize(1620, 940)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QWidget()
        header.setObjectName("surface")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(10)
        layout.addWidget(header)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        header_layout.addLayout(title_row)

        title_label = QLabel("分析工作台")
        title_label.setProperty("role", "hero-title")
        title_row.addWidget(title_label)
        title_row.addStretch(1)

        self.maximize_button = QPushButton("最大化")
        self.maximize_button.setProperty("variant", "secondary")
        self.maximize_button.clicked.connect(self._toggle_maximized)
        title_row.addWidget(self.maximize_button)

        subtitle_label = QLabel(f"当前文件：{self.session.file_name}")
        subtitle_label.setProperty("role", "caption")
        header_layout.addWidget(subtitle_label)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        header_layout.addLayout(status_row)

        self.analysis_type_label = QLabel("分析类型：未选择")
        self.analysis_type_label.setProperty("role", "status")
        status_row.addWidget(self.analysis_type_label)

        self.node_status_label = QLabel("节点：请选择一个分析项")
        self.node_status_label.setProperty("role", "status")
        status_row.addWidget(self.node_status_label)

        self.compute_status_label = QLabel("状态：等待选择")
        self.compute_status_label.setProperty("role", "status")
        status_row.addWidget(self.compute_status_label)
        status_row.addStretch(1)

        set_status_tone(self.analysis_type_label, "info")
        set_status_tone(self.node_status_label, "info")
        set_status_tone(self.compute_status_label, "warn")

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.content_splitter = splitter
        layout.addWidget(splitter, 1)

        navigation_group = QGroupBox("分析导航")
        navigation_group.setMinimumWidth(280)
        self.navigation_group = navigation_group
        navigation_layout = QVBoxLayout(navigation_group)
        navigation_hint = QLabel("从左侧选择一个具体分析节点，中央会展示结果，右侧可调整这一类分析参数。")
        navigation_hint.setProperty("role", "caption")
        navigation_hint.setWordWrap(True)
        navigation_layout.addWidget(navigation_hint)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["分析树"])
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        navigation_layout.addWidget(self.tree, 1)
        splitter.addWidget(navigation_group)

        preview_group = QGroupBox("结果预览")
        preview_group.setMinimumWidth(760)
        self.preview_group = preview_group
        preview_layout = QVBoxLayout(preview_group)
        self.preview = PreviewWidget()
        preview_layout.addWidget(self.preview)
        splitter.addWidget(preview_group)

        parameter_group = QGroupBox("参数设置")
        parameter_group.setMinimumWidth(320)
        self.parameter_group = parameter_group
        parameter_layout = QVBoxLayout(parameter_group)
        self.parameter_panel = ParameterPanel()
        parameter_layout.addWidget(self.parameter_panel)
        splitter.addWidget(parameter_group)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(400)
        self._debounce_timer.timeout.connect(self._on_debounce_recompute)
        self.parameter_panel.values_changed.connect(self._on_param_changed)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([320, 940, 360])

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        layout.addLayout(buttons)

        self.apply_button = QPushButton("应用到这一类分析")
        self.apply_button.clicked.connect(self._on_apply_clicked)
        buttons.addWidget(self.apply_button)

        self.reset_button = QPushButton("恢复这一类分析默认值")
        self.reset_button.setProperty("variant", "secondary")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        buttons.addWidget(self.reset_button)

        buttons.addStretch(1)

        self.export_current_figure_button = QPushButton("导出当前图形")
        self.export_current_figure_button.setProperty("variant", "secondary")
        self.export_current_figure_button.clicked.connect(self._on_export_figure)
        buttons.addWidget(self.export_current_figure_button)
        self.export_image_button = self.export_current_figure_button

        self.export_current_data_button = QPushButton("导出当前数据")
        self.export_current_data_button.setProperty("variant", "secondary")
        self.export_current_data_button.clicked.connect(self._on_export_data)
        buttons.addWidget(self.export_current_data_button)
        self.export_data_button = self.export_current_data_button

        self.export_all_figures_button = QPushButton("导出全部图形")
        self.export_all_figures_button.setProperty("variant", "secondary")
        self.export_all_figures_button.clicked.connect(self._on_export_all_figures)
        buttons.addWidget(self.export_all_figures_button)

        self.export_all_data_button = QPushButton("导出全部数据")
        self.export_all_data_button.setProperty("variant", "secondary")
        self.export_all_data_button.clicked.connect(self._on_export_all_data)
        buttons.addWidget(self.export_all_data_button)

        self.cancel_export_button = QPushButton("取消导出")
        self.cancel_export_button.setProperty("variant", "secondary")
        self.cancel_export_button.clicked.connect(self._cancel_export)
        self.cancel_export_button.setEnabled(False)
        buttons.addWidget(self.cancel_export_button)

        self.export_progress_bar = QProgressBar()
        self.export_progress_bar.setRange(0, 100)
        self.export_progress_bar.setValue(0)
        layout.addWidget(self.export_progress_bar)

        self.export_status_view = QTextEdit()
        self.export_status_view.setReadOnly(True)
        self.export_status_view.setMinimumHeight(110)
        layout.addWidget(self.export_status_view)

        self._populate_tree()
        self.tree.collapseAll()
        self._refresh_export_buttons()
        self._refresh_maximize_button()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._refresh_maximize_button()

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._refresh_maximize_button()

    def _refresh_maximize_button(self) -> None:
        if self.maximize_button is None:
            return
        is_maximized = self.isMaximized()
        self.maximize_button.setText("还原" if is_maximized else "最大化")
        self.maximize_button.setToolTip("恢复窗口大小" if is_maximized else "将分析工作台最大化显示")

    def _populate_tree(self) -> None:
        self.tree.clear()
        self._add_node(None, self.tree_root)

    def _add_node(self, parent_item: QTreeWidgetItem | None, node: AnalysisNode) -> None:
        if node.node_id == "root":
            for child in node.children:
                self._add_node(None, child)
            return
        item = QTreeWidgetItem([node.label])
        item.setData(0, Qt.UserRole, node.node_id)
        if parent_item is None:
            self.tree.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
        for child in node.children:
            self._add_node(item, child)

    def _on_tree_selection_changed(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        node_id = items[0].data(0, Qt.UserRole)
        self.current_node = self.tree_root.find_node(node_id)
        self._update_context_labels()
        values = (
            self.profile.resolved_params(self.current_node.analysis_key, self.current_node.node_id)
            if self.current_node.analysis_key
            else {}
        )
        self.parameter_panel.set_analysis(self.current_node.analysis_key, values)
        self._compute_current_node(values if self.current_node.analysis_key else None, show_validation_dialog=False)

    def _update_context_labels(self) -> None:
        if self.current_node is None or self.current_node.analysis_key is None:
            self.analysis_type_label.setText("分析类型：未选择")
            self.node_status_label.setText("节点：请选择一个分析项")
            set_status_tone(self.analysis_type_label, "info")
            set_status_tone(self.node_status_label, "info")
            return
        definition = get_analysis_definition(self.current_node.analysis_key)
        self.analysis_type_label.setText(f"分析类型：{definition.label}")
        self.node_status_label.setText(f"节点：{self.current_node.label}")
        set_status_tone(self.analysis_type_label, "info")
        set_status_tone(self.node_status_label, "info")

    def _on_param_changed(self) -> None:
        self._debounce_timer.start()

    def _on_debounce_recompute(self) -> None:
        if not self.current_node or not self.current_node.analysis_key:
            return
        params = self.parameter_panel.values()
        self._compute_current_node(params, show_validation_dialog=False)

    def _on_apply_clicked(self) -> None:
        if not self.current_node or not self.current_node.analysis_key:
            return
        params = self.parameter_panel.values()
        if not self._compute_current_node(params, show_validation_dialog=True):
            return
        self.profile.set_analysis_defaults(self.current_node.analysis_key, params)
        self.compute_status_label.setText("状态：已更新这一类分析参数")
        set_status_tone(self.compute_status_label, "ok")

    def _on_reset_clicked(self) -> None:
        if not self.current_node or not self.current_node.analysis_key:
            return
        defaults = self.profile.reset_analysis_defaults(self.current_node.analysis_key)
        self.parameter_panel.apply_values(defaults)
        self._compute_current_node(defaults, show_validation_dialog=True)
        self.compute_status_label.setText("状态：已恢复这一类分析默认值")
        set_status_tone(self.compute_status_label, "ok")

    def _compute_current_node(self, runtime_overrides: dict | None, show_validation_dialog: bool) -> bool:
        if not self.current_node:
            return False

        params = runtime_overrides or {}
        if self.current_node.analysis_key:
            try:
                validate_analysis_request(self.session, self.current_node, params)
            except ValueError as exc:
                self.current_result = None
                self._set_export_enabled(False)
                self.preview.show_message(str(exc), title="结果预览")
                self.compute_status_label.setText("状态：参数无效")
                set_status_tone(self.compute_status_label, "error")
                if show_validation_dialog:
                    QMessageBox.warning(self, "参数无效", str(exc))
                return False

        self._latest_request_id += 1
        request_id = self._latest_request_id
        self.thread_pool.clear()
        self.current_result = None
        self._set_export_enabled(False)
        self.preview.show_message("正在计算，请稍候…", title="正在更新结果")
        self.compute_status_label.setText("状态：正在计算")
        set_status_tone(self.compute_status_label, "warn")
        worker = AnalysisWorker(request_id, self.service.compute, self.session, self.current_node, self.profile, params)
        worker.signals.result.connect(self._on_result_ready)
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)
        return True

    def _on_result_ready(self, request_id: int, result: AnalysisResult) -> None:
        if request_id != self._latest_request_id:
            return
        self.current_result = result
        self._set_export_enabled(True)
        self.preview.render(result)
        self.compute_status_label.setText("状态：结果已更新")
        set_status_tone(self.compute_status_label, "ok")

    def _on_worker_error(self, request_id: int, message: str) -> None:
        if request_id != self._latest_request_id:
            return
        self.current_result = None
        self._set_export_enabled(False)
        user_message = friendly_error_message(message)
        self.preview.show_message(user_message, title="计算失败")
        self.compute_status_label.setText("状态：计算失败")
        set_status_tone(self.compute_status_label, "error")
        QMessageBox.warning(self, "分析失败", user_message)

    def _on_export_figure(self) -> None:
        if self.current_result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出图形",
            str(self._default_figure_export_path()),
            self._figure_dialog_filter(),
        )
        if not path:
            return
        export_result_figure(self.current_result, path)

    def _on_export_data(self) -> None:
        if self.current_result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出数据",
            str(self._default_data_export_path()),
            self._data_dialog_filter(),
        )
        if not path:
            return
        export_result_data(self.current_result, path)

    def _on_export_all_figures(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "导出全部图形", str(self._export_base_dir()))
        if not output_dir:
            return
        self._start_export_all(Path(output_dir), export_figures=True, export_data=False)

    def _on_export_all_data(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "导出全部数据", str(self._export_base_dir()))
        if not output_dir:
            return
        self._start_export_all(Path(output_dir), export_figures=False, export_data=True)

    def _on_export_all_finished(self) -> None:
        self._export_busy = False
        self.cancel_export_button.setEnabled(False)
        self._refresh_export_buttons()

    def _set_export_enabled(self, enabled: bool) -> None:
        self._refresh_export_buttons()

    def _refresh_export_buttons(self) -> None:
        current_enabled = self.current_result is not None and not self._export_busy
        all_enabled = self._has_exportable_nodes() and not self._export_busy
        self.export_current_figure_button.setEnabled(current_enabled)
        self.export_current_data_button.setEnabled(current_enabled)
        self.export_all_figures_button.setEnabled(all_enabled)
        self.export_all_data_button.setEnabled(all_enabled)

    def _default_figure_export_path(self) -> Path:
        return self._export_base_dir() / f"{self._default_export_stem()}.{self._preferred_figure_format()}"

    def _default_data_export_path(self) -> Path:
        return self._export_base_dir() / f"{self._default_export_stem()}.{self._preferred_data_format()}"

    def _export_base_dir(self) -> Path:
        parent = self.session.file_path.parent
        return parent if parent.exists() else Path.cwd()

    def _default_export_stem(self) -> str:
        if self.current_node is not None and self.current_node.analysis_key is not None:
            stem = build_analysis_output_stem(self.session, self.current_node)
            if stem:
                return stem
        if self.current_result is not None:
            stem = slugify_export_token(self.current_result.title or self.current_result.node_id)
            if stem:
                return stem
        return "analysis"

    def _preferred_figure_format(self) -> str:
        for raw_format in self.profile.export_defaults.get("figure_formats", []):
            normalized = str(raw_format).lower().lstrip(".")
            if normalized in {"png", "svg"}:
                return normalized
        return "png"

    def _preferred_data_format(self) -> str:
        return "csv"

    def _figure_dialog_filter(self) -> str:
        formats: list[str] = []
        for raw_format in self.profile.export_defaults.get("figure_formats", []):
            normalized = str(raw_format).lower().lstrip(".")
            if normalized in {"png", "svg"} and normalized not in formats:
                formats.append(normalized)
        if not formats:
            formats = ["png", "svg"]
        patterns = " ".join(f"*.{file_format}" for file_format in formats)
        return f"Images ({patterns})"

    def _data_dialog_filter(self) -> str:
        return "CSV (*.csv)"

    def _has_exportable_nodes(self) -> bool:
        return any(self._iter_exportable_nodes(self.tree_root))

    def _iter_exportable_nodes(self, node: AnalysisNode):
        if node.analysis_key is not None:
            yield node
        for child in node.children:
            yield from self._iter_exportable_nodes(child)

    def _start_export_all(self, output_dir: Path, export_figures: bool, export_data: bool) -> None:
        if not self._has_exportable_nodes():
            QMessageBox.information(self, "导出结果", "当前工作台没有可导出的分析节点。")
            return
        self._export_busy = True
        self._refresh_export_buttons()
        self.cancel_export_button.setEnabled(True)
        scope_label = self._export_scope_label(export_figures, export_data)
        self.export_progress_bar.setValue(0)
        self.export_status_view.setPlainText(f"正在准备导出{scope_label}…")
        self.compute_status_label.setText(f"状态：正在导出全部{scope_label}")
        set_status_tone(self.compute_status_label, "warn")

        self._export_cancellation_token = CancellationToken()
        worker = TaskWorker(
            self._execute_export_all,
            output_dir,
            export_figures=export_figures,
            export_data=export_data,
            profile_snapshot=self.profile.clone(),
            inject_progress=True,
            cancellation_token=self._export_cancellation_token,
        )
        worker.signals.progress.connect(self._on_export_all_progress)
        worker.signals.result.connect(
            lambda report, figures=export_figures, data=export_data: self._on_export_all_success(report, figures, data)
        )
        worker.signals.error.connect(self._on_export_all_error)
        worker.signals.cancelled.connect(self._on_export_cancelled)
        worker.signals.finished.connect(self._on_export_all_finished)
        self.export_thread_pool.start(worker)

    def _execute_export_all(
        self,
        output_dir: Path,
        export_figures: bool = True,
        export_data: bool = True,
        profile_snapshot: SessionProfile | None = None,
        progress_callback=None,
        cancellation_token: CancellationToken | None = None,
    ) -> ExportAllOutcome:
        export_profile = profile_snapshot.clone() if profile_snapshot is not None else self.profile.clone()
        export_service = self.service.clone()
        runner = BatchAnalysisRunner(service=export_service)
        report = runner.export_session(
            self.session,
            output_dir,
            export_profile,
            export_figures=export_figures,
            export_data=export_data,
            progress_callback=progress_callback,
            cancellation_token=cancellation_token,
        )
        return ExportAllOutcome(report=report, service=export_service)

    def _on_export_all_progress(self, update: BatchProgressUpdate) -> None:
        self.export_progress_bar.setValue(update.progress_percent)
        lines = [
            f"阶段：{self._export_phase_label(update.phase)}",
            f"进度：{update.completed_tasks} / {update.total_tasks}" if update.total_tasks else "进度：准备中",
            f"成功任务：{update.success_count}",
            f"失败任务：{update.failure_count}",
        ]
        if update.total_chunks:
            lines.append(f"批次：{min(update.completed_chunks + 1, update.total_chunks)} / {update.total_chunks}")
        if update.current_file is not None:
            lines.append(f"当前文件：{update.current_file.name}")
        if update.current_task:
            lines.append(f"当前任务：{update.current_task}")
        if update.eta_seconds is not None:
            lines.append(f"预计剩余：{self._format_duration(update.eta_seconds)}")
        if update.message:
            lines.append(f"详情：{update.message}")
        self.export_status_view.setPlainText("\n".join(lines))

    def _on_export_all_success(self, outcome: ExportAllOutcome, export_figures: bool, export_data: bool) -> None:
        report = outcome.report
        scope_label = self._export_scope_label(export_figures, export_data)
        self.export_progress_bar.setValue(100)
        self.export_status_view.setPlainText(
            "\n".join(
                [
                    f"已完成全部{scope_label}导出。",
                    f"成功任务：{report.success_count}",
                    f"失败任务：{report.failure_count}",
                    f"汇总清单：{report.run_summary_path}",
                    f"失败清单：{report.failures_path}",
                ]
            )
        )
        if report.failure_count == 0:
            self.compute_status_label.setText(f"状态：已导出全部{scope_label}")
            set_status_tone(self.compute_status_label, "ok")
            dialog = QMessageBox.information
        else:
            self.compute_status_label.setText(f"状态：全部{scope_label}导出完成，部分失败")
            set_status_tone(self.compute_status_label, "warn")
            dialog = QMessageBox.warning

        dialog(
            self,
            f"导出全部{scope_label}",
            "\n".join(
                [
                    f"已完成全部{scope_label}导出。",
                    f"成功任务：{report.success_count}",
                    f"失败任务：{report.failure_count}",
                    f"汇总清单：{report.run_summary_path}",
                    f"失败清单：{report.failures_path}",
                ]
            ),
        )

    def _on_export_all_error(self, message: str) -> None:
        self.export_status_view.setPlainText(f"导出失败：{message}")
        self.compute_status_label.setText("状态：全量导出失败")
        set_status_tone(self.compute_status_label, "error")
        QMessageBox.critical(self, "导出失败", message)

    def _cancel_export(self) -> None:
        if hasattr(self, "_export_cancellation_token"):
            self._export_cancellation_token.cancel()
        self.cancel_export_button.setEnabled(False)
        self.export_status_view.append("正在取消…")

    def _on_export_cancelled(self) -> None:
        self.export_status_view.setPlainText("导出已被用户取消。")
        self.export_progress_bar.setValue(0)
        self.compute_status_label.setText("状态：导出已取消")
        set_status_tone(self.compute_status_label, "info")

    @staticmethod
    def _export_phase_label(phase: str) -> str:
        labels = {
            "starting": "准备中",
            "processing": "处理中",
            "finished": "已完成",
        }
        return labels.get(phase, phase)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        rounded = max(0, int(round(seconds)))
        minutes, remaining_seconds = divmod(rounded, 60)
        hours, remaining_minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}h {remaining_minutes}m"
        if minutes > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{remaining_seconds}s"

    @staticmethod
    def _export_scope_label(export_figures: bool, export_data: bool) -> str:
        if export_figures and export_data:
            return "图形和数据"
        if export_figures:
            return "图形"
        return "数据"
