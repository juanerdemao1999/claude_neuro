from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import SessionProfile
from ..grouped_plv import GroupedPLVManifestEntry, GroupedPLVParams, GroupedPLVRunResult, GroupedPLVRunner
from .preview import PreviewWidget
from .theme import ensure_app_theme, set_status_tone
from .workers import TaskWorker


class GroupedPLVWorkspaceDialog(QDialog):
    def __init__(
        self,
        profile: SessionProfile,
        parent: QWidget | None = None,
        runner: GroupedPLVRunner | None = None,
        initial_entries: list[GroupedPLVManifestEntry] | None = None,
    ) -> None:
        super().__init__(parent)
        ensure_app_theme()

        self.profile = profile
        self.runner = runner or GroupedPLVRunner()
        self.current_run_result: GroupedPLVRunResult | None = None
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(1)

        self.setWindowTitle("分组 PLV 工作台")
        self.resize(1520, 960)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QWidget()
        header.setObjectName("surface")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(8)
        layout.addWidget(header)

        title_label = QLabel("分组 PLV 工作台")
        title_label.setProperty("role", "hero-title")
        header_layout.addWidget(title_label)

        subtitle_label = QLabel(
            "先把多个 NEX5 文件加入下方表格，再在 GUI 里勾选要分析的数据，并填写分组、被试和脑区信息。"
            "运行后会输出分组 PLV 的极坐标图，以及单位级、被试级、组级统计表。"
        )
        subtitle_label.setProperty("role", "caption")
        subtitle_label.setWordWrap(True)
        header_layout.addWidget(subtitle_label)

        self.status_label = QLabel("状态：等待运行")
        self.status_label.setProperty("role", "status")
        set_status_tone(self.status_label, "info")
        header_layout.addWidget(self.status_label)

        content = QGridLayout()
        content.setHorizontalSpacing(14)
        content.setVerticalSpacing(14)
        layout.addLayout(content, 1)

        controls_group = QGroupBox("文件与参数")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setSpacing(12)
        content.addWidget(controls_group, 0, 0)

        path_form = QFormLayout()
        path_form.setHorizontalSpacing(12)
        path_form.setVerticalSpacing(10)
        controls_layout.addLayout(path_form)

        self.input_dir_edit = QLineEdit(self.profile.input_defaults.get("grouped_plv_input_dir", ""))
        self.output_dir_edit = QLineEdit(self.profile.input_defaults.get("grouped_plv_output_dir", ""))
        path_form.addRow("数据目录", self._path_row(self.input_dir_edit, self._choose_input_dir))
        path_form.addRow("输出目录", self._path_row(self.output_dir_edit, self._choose_output_dir))

        source_group = QGroupBox("待分析文件")
        source_layout = QVBoxLayout(source_group)
        source_layout.setSpacing(10)
        controls_layout.addWidget(source_group, 1)

        source_hint = QLabel(
            "推荐流程：先点“添加文件”或“导入目录”，把数据放进表格；"
            "再针对你关心的文件填写分组信息，必要时可复制某一行做不同条件的分组。"
        )
        source_hint.setProperty("role", "caption")
        source_hint.setWordWrap(True)
        source_layout.addWidget(source_hint)

        source_button_row = QHBoxLayout()
        source_button_row.setSpacing(8)
        source_layout.addLayout(source_button_row)

        add_files_button = QPushButton("添加文件")
        add_files_button.clicked.connect(self._add_files)
        source_button_row.addWidget(add_files_button)

        add_directory_button = QPushButton("导入目录")
        add_directory_button.setProperty("variant", "secondary")
        add_directory_button.clicked.connect(self._add_directory_files)
        source_button_row.addWidget(add_directory_button)

        duplicate_button = QPushButton("复制所选行")
        duplicate_button.setProperty("variant", "secondary")
        duplicate_button.clicked.connect(self._duplicate_selected_rows)
        source_button_row.addWidget(duplicate_button)

        remove_button = QPushButton("删除所选行")
        remove_button.setProperty("variant", "secondary")
        remove_button.clicked.connect(self._remove_selected_rows)
        source_button_row.addWidget(remove_button)

        clear_button = QPushButton("清空表格")
        clear_button.setProperty("variant", "secondary")
        clear_button.clicked.connect(self._clear_rows)
        source_button_row.addWidget(clear_button)

        self.file_table = QTableWidget(0, 5)
        self.file_table.setHorizontalHeaderLabels(["启用", "文件路径", "分组", "被试", "脑区"])
        self.file_table.horizontalHeader().setStretchLastSection(True)
        source_layout.addWidget(self.file_table, 1)

        params_group = QGroupBox("PLV 参数")
        params_form = QFormLayout(params_group)
        params_form.setHorizontalSpacing(12)
        params_form.setVerticalSpacing(10)
        controls_layout.addWidget(params_group)

        self.low_hz_spin = self._make_float_spin(0.1, 500.0, 0.1, 4.0)
        self.high_hz_spin = self._make_float_spin(0.1, 500.0, 0.1, 12.0)
        self.phase_bins_spin = self._make_int_spin(6, 72, 1, 18)
        self.filter_order_spin = self._make_int_spin(1, 12, 1, 4)
        self.min_spikes_spin = self._make_int_spin(1, 50000, 1, 5)
        self.align_phase_check = QCheckBox()
        self.align_phase_check.setChecked(True)
        self.same_region_only_check = QCheckBox()
        self.same_region_only_check.setChecked(True)
        params_form.addRow("低频截止 (Hz)", self.low_hz_spin)
        params_form.addRow("高频截止 (Hz)", self.high_hz_spin)
        params_form.addRow("相位分箱数", self.phase_bins_spin)
        params_form.addRow("滤波器阶数", self.filter_order_spin)
        params_form.addRow("每个单元最少脉冲数", self.min_spikes_spin)
        params_form.addRow("按首选相位对齐", self.align_phase_check)
        params_form.addRow("仅匹配同脑区", self.same_region_only_check)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        controls_layout.addLayout(button_row)

        self.run_button = QPushButton("运行分组 PLV")
        self.run_button.clicked.connect(self._run_grouped_plv)
        button_row.addWidget(self.run_button)

        self.export_button = QPushButton("导出结果")
        self.export_button.setProperty("variant", "secondary")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_outputs)
        button_row.addWidget(self.export_button)
        button_row.addStretch(1)

        self.status_view = QTextEdit()
        self.status_view.setReadOnly(True)
        self.status_view.setMinimumHeight(180)
        controls_layout.addWidget(self.status_view)

        preview_group = QGroupBox("结果预览")
        preview_layout = QVBoxLayout(preview_group)
        self.preview = PreviewWidget()
        self.preview.show_message("把文件加入表格并运行后，这里会显示分组 PLV 的极坐标结果。", title="分组 PLV 预览")
        preview_layout.addWidget(self.preview)
        content.addWidget(preview_group, 0, 1)
        content.setColumnStretch(0, 3)
        content.setColumnStretch(1, 5)

        for entry in initial_entries or []:
            self._append_entry_row(entry.file_path, group=entry.group, subject=entry.subject, region=entry.region)

    def _path_row(self, line_edit: QLineEdit, browse_callback) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(line_edit, 1)
        button = QPushButton("浏览")
        button.setProperty("variant", "secondary")
        button.clicked.connect(browse_callback)
        layout.addWidget(button)
        return row

    @staticmethod
    def _make_float_spin(minimum: float, maximum: float, step: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(4)
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setValue(value)
        return spin

    @staticmethod
    def _make_int_spin(minimum: int, maximum: int, step: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setValue(value)
        return spin

    def _choose_input_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "选择数据目录",
            self.input_dir_edit.text().strip() or str(Path.cwd()),
        )
        if path:
            self.input_dir_edit.setText(path)

    def _choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "选择输出目录",
            self.output_dir_edit.text().strip() or str(Path.cwd()),
        )
        if path:
            self.output_dir_edit.setText(path)

    def _add_files(self) -> None:
        base_dir = self.input_dir_edit.text().strip() or str(Path.cwd())
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 NEX5 文件", base_dir, "NEX5 文件 (*.nex5)")
        for raw_path in paths:
            self._append_entry_row(Path(raw_path))

    def _add_directory_files(self) -> None:
        directory = self.input_dir_edit.text().strip()
        if not directory:
            directory = QFileDialog.getExistingDirectory(self, "选择数据目录", str(Path.cwd()))
            if not directory:
                return
            self.input_dir_edit.setText(directory)
        for file_path in sorted(Path(directory).glob("*.nex5")):
            self._append_entry_row(file_path)

    def _append_entry_row(
        self,
        file_path: Path,
        *,
        group: str = "第 1 组",
        subject: str | None = None,
        region: str | None = None,
        checked: bool = True,
    ) -> None:
        normalized_path = Path(file_path)
        for row_index in range(self.file_table.rowCount()):
            existing_item = self.file_table.item(row_index, 1)
            if existing_item is not None and Path(existing_item.text()) == normalized_path:
                return

        row_index = self.file_table.rowCount()
        self.file_table.insertRow(row_index)

        use_item = QTableWidgetItem()
        use_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
        use_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.file_table.setItem(row_index, 0, use_item)

        file_item = QTableWidgetItem(str(normalized_path))
        file_item.setFlags(file_item.flags() & ~Qt.ItemIsEditable)
        self.file_table.setItem(row_index, 1, file_item)

        default_subject = subject or normalized_path.stem
        self.file_table.setItem(row_index, 2, QTableWidgetItem(group))
        self.file_table.setItem(row_index, 3, QTableWidgetItem(default_subject))
        self.file_table.setItem(row_index, 4, QTableWidgetItem(region or ""))
        self.file_table.resizeColumnsToContents()

    def _duplicate_selected_rows(self) -> None:
        rows = sorted({index.row() for index in self.file_table.selectedIndexes()})
        for row in rows:
            checked = self.file_table.item(row, 0).checkState() == Qt.Checked
            file_path = self.file_table.item(row, 1).text()
            group = self.file_table.item(row, 2).text()
            subject = self.file_table.item(row, 3).text()
            region = self.file_table.item(row, 4).text()

            row_index = self.file_table.rowCount()
            self.file_table.insertRow(row_index)

            use_item = QTableWidgetItem()
            use_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            use_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self.file_table.setItem(row_index, 0, use_item)

            file_item = QTableWidgetItem(file_path)
            file_item.setFlags(file_item.flags() & ~Qt.ItemIsEditable)
            self.file_table.setItem(row_index, 1, file_item)
            self.file_table.setItem(row_index, 2, QTableWidgetItem(group))
            self.file_table.setItem(row_index, 3, QTableWidgetItem(subject))
            self.file_table.setItem(row_index, 4, QTableWidgetItem(region))

    def _remove_selected_rows(self) -> None:
        for row in sorted({index.row() for index in self.file_table.selectedIndexes()}, reverse=True):
            self.file_table.removeRow(row)

    def _clear_rows(self) -> None:
        self.file_table.setRowCount(0)

    def _current_params(self) -> GroupedPLVParams:
        return GroupedPLVParams(
            low_hz=float(self.low_hz_spin.value()),
            high_hz=float(self.high_hz_spin.value()),
            phase_bins=int(self.phase_bins_spin.value()),
            filter_order=int(self.filter_order_spin.value()),
            min_spikes_per_unit=int(self.min_spikes_spin.value()),
            align_preferred_phase=self.align_phase_check.isChecked(),
            same_region_only=self.same_region_only_check.isChecked(),
        )

    def _entries_from_table(self) -> list[GroupedPLVManifestEntry]:
        entries: list[GroupedPLVManifestEntry] = []
        for row_index in range(self.file_table.rowCount()):
            use_item = self.file_table.item(row_index, 0)
            if use_item is None or use_item.checkState() != Qt.Checked:
                continue

            file_item = self.file_table.item(row_index, 1)
            group_item = self.file_table.item(row_index, 2)
            subject_item = self.file_table.item(row_index, 3)
            region_item = self.file_table.item(row_index, 4)

            file_path = Path(file_item.text().strip()) if file_item is not None else Path()
            group = group_item.text().strip() if group_item is not None else ""
            subject = subject_item.text().strip() if subject_item is not None else ""
            region = region_item.text().strip() if region_item is not None else ""

            if not str(file_path).strip():
                raise ValueError(f"第 {row_index + 1} 行缺少文件路径。")
            if not file_path.exists():
                raise ValueError(f"第 {row_index + 1} 行的文件不存在：{file_path}")
            if not group:
                raise ValueError(f"第 {row_index + 1} 行缺少分组名称。")

            entries.append(
                GroupedPLVManifestEntry(
                    file_path=file_path,
                    group=group,
                    subject=subject or None,
                    region=region or None,
                )
            )
        return entries

    def _run_grouped_plv(self) -> None:
        try:
            entries = self._entries_from_table()
        except ValueError as exc:
            QMessageBox.warning(self, "分组 PLV", str(exc))
            return

        if not entries:
            QMessageBox.warning(self, "分组 PLV", "请先把要分析的文件加入表格，并勾选至少一行。")
            return

        self.profile.input_defaults["grouped_plv_input_dir"] = self.input_dir_edit.text().strip()
        self.profile.input_defaults["grouped_plv_output_dir"] = self.output_dir_edit.text().strip()
        self.run_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.status_label.setText("状态：正在运行分组 PLV")
        set_status_tone(self.status_label, "warn")
        self.status_view.setPlainText("正在根据表格中的文件与分组信息汇总分组 PLV，请稍候。")

        worker = TaskWorker(
            self.runner.run_entries,
            entries,
            self.profile.clone(),
            self._current_params(),
        )
        worker.signals.result.connect(self._on_run_success)
        worker.signals.error.connect(self._on_task_error)
        worker.signals.finished.connect(self._on_run_finished)
        self.thread_pool.start(worker)

    def _export_outputs(self) -> None:
        if self.current_run_result is None:
            return

        output_dir = self.output_dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "分组 PLV", "请选择输出目录。")
            return

        self.profile.input_defaults["grouped_plv_output_dir"] = output_dir
        self.export_button.setEnabled(False)
        self.status_label.setText("状态：正在导出结果")
        set_status_tone(self.status_label, "warn")

        worker = TaskWorker(self.runner.export_run, self.current_run_result, Path(output_dir))
        worker.signals.result.connect(self._on_export_success)
        worker.signals.error.connect(self._on_task_error)
        worker.signals.finished.connect(self._on_export_finished)
        self.thread_pool.start(worker)

    def _on_run_success(self, result: GroupedPLVRunResult) -> None:
        self.current_run_result = result
        self.preview.render(result.preview_result)
        self.export_button.setEnabled(True)
        self.status_label.setText("状态：运行完成")
        set_status_tone(self.status_label, "ok")

        lines = [
            "分组 PLV 已完成。",
            f"已选文件数：{len(result.manifest_entries)}",
            f"单位级记录数：{len(result.unit_level)}",
            f"被试级记录数：{len(result.subject_level)}",
            f"组级记录数：{len(result.group_level)}",
            f"跳过文件数：{len(result.failures)}",
        ]
        if result.failures:
            lines.append("")
            lines.append("跳过详情：")
            for failure in result.failures:
                lines.append(f"- {failure.file_path.name}: {failure.message}")
        self.status_view.setPlainText("\n".join(lines))

    def _on_export_success(self, paths: dict[str, Path]) -> None:
        lines = [self.status_view.toPlainText().strip(), "", "导出完成："]
        for key, path in paths.items():
            lines.append(f"- {key}: {path}")
        self.status_view.setPlainText("\n".join(line for line in lines if line))
        self.status_label.setText("状态：导出完成")
        set_status_tone(self.status_label, "ok")

    def _on_task_error(self, message: str) -> None:
        self.status_label.setText("状态：运行失败")
        set_status_tone(self.status_label, "error")
        self.status_view.setPlainText(message)
        QMessageBox.critical(self, "分组 PLV", message)

    def _on_run_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.export_button.setEnabled(self.current_run_result is not None)

    def _on_export_finished(self) -> None:
        self.export_button.setEnabled(self.current_run_result is not None)
