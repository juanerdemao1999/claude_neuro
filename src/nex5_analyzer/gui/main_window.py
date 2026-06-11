from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..analysis.batch import BatchAnalysisRunner, BatchProgressUpdate, BatchRunReport
from ..analysis.registry import iter_analysis_definitions
from ..config import SessionProfile, default_autosave_profile_path
from ..grouped_plv import GroupedPLVManifestEntry
from ..io.nex5_loader import Nex5SessionLoader
from ..models import RegionMapping, SessionData, normalize_region_assignment
from .analysis_dialog import AnalysisWorkspaceDialog
from .grouped_plv_dialog import GroupedPLVWorkspaceDialog
from .region_mapping_dialog import ChannelRegionMappingDialog, validate_region_map
from .theme import ensure_app_theme, set_status_tone
from .workers import TaskWorker


class MainWindow(QMainWindow):
    def __init__(self, autosave_profile_path: Path | None = None) -> None:
        super().__init__()
        ensure_app_theme()

        self.loader = Nex5SessionLoader()
        self.batch_runner = BatchAnalysisRunner()
        self.profile = SessionProfile.default()
        self.current_profile_path: Path | None = None
        self.autosave_profile_path = autosave_profile_path or default_autosave_profile_path()
        self.session: SessionData | None = None
        self.current_file_path: Path | None = None
        self.batch_thread_pool = QThreadPool(self)
        self.batch_analysis_checkboxes: dict[str, QCheckBox] = {}
        self._restore_persisted_profile_state()

        self.setWindowTitle("NEX5 Spike/LFP Analyzer")
        self.resize(1280, 960)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QWidget()
        header.setObjectName("surface")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(12)
        layout.addWidget(header)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        header_layout.addLayout(title_row)

        title_column = QVBoxLayout()
        title_column.setSpacing(4)
        title_row.addLayout(title_column, 1)

        hero_title = QLabel("NEX5 Spike / LFP Analyzer")
        hero_title.setProperty("role", "hero-title")
        title_column.addWidget(hero_title)

        hero_subtitle = QLabel("先完成脑区映射，再进入单文件分析或批量处理。")
        hero_subtitle.setProperty("role", "caption")
        title_column.addWidget(hero_subtitle)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        title_row.addLayout(action_row)

        load_file_button = QPushButton("加载 NEX5")
        load_file_button.clicked.connect(self._choose_file)
        action_row.addWidget(load_file_button)

        load_profile_button = QPushButton("加载配置")
        load_profile_button.setProperty("variant", "secondary")
        load_profile_button.clicked.connect(self._choose_profile)
        action_row.addWidget(load_profile_button)

        save_profile_button = QPushButton("保存配置")
        save_profile_button.setProperty("variant", "secondary")
        save_profile_button.clicked.connect(self._save_profile)
        action_row.addWidget(save_profile_button)

        self.open_workspace_button = QPushButton("打开分析工作台")
        self.open_workspace_button.clicked.connect(self._open_workspace)
        self.open_workspace_button.setEnabled(False)
        action_row.addWidget(self.open_workspace_button)

        self.open_grouped_plv_button = QPushButton("打开分组 PLV")
        self.open_grouped_plv_button.setProperty("variant", "secondary")
        self.open_grouped_plv_button.clicked.connect(self._open_grouped_plv_workspace)
        self.open_grouped_plv_button.setEnabled(True)
        action_row.addWidget(self.open_grouped_plv_button)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        header_layout.addLayout(status_row)

        self.file_status_label = QLabel("文件：未加载")
        self.file_status_label.setProperty("role", "status")
        status_row.addWidget(self.file_status_label)

        self.profile_status_label = QLabel("配置：内存配置")
        self.profile_status_label.setProperty("role", "status")
        status_row.addWidget(self.profile_status_label)

        self.mapping_status_label = QLabel("映射：等待加载文件")
        self.mapping_status_label.setProperty("role", "status")
        status_row.addWidget(self.mapping_status_label)
        status_row.addStretch(1)

        set_status_tone(self.file_status_label, "info")
        set_status_tone(self.profile_status_label, "info")
        set_status_tone(self.mapping_status_label, "warn")

        content_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(content_splitter, 1)

        summary_group = QGroupBox("样本摘要")
        summary_layout = QVBoxLayout(summary_group)

        summary_hint = QLabel("这里展示当前样本的时长、采样率、通道数量以及识别结果。")
        summary_hint.setProperty("role", "caption")
        summary_hint.setWordWrap(True)
        summary_layout.addWidget(summary_hint)

        self.metadata_view = QTextEdit()
        self.metadata_view.setReadOnly(True)
        self.metadata_view.setPlaceholderText("加载 NEX5 文件后，这里会显示样本摘要。")
        summary_layout.addWidget(self.metadata_view, 1)
        content_splitter.addWidget(summary_group)

        mapping_group = QGroupBox("脑区通道映射")
        mapping_layout = QVBoxLayout(mapping_group)

        mapping_header = QHBoxLayout()
        mapping_header.setSpacing(10)
        mapping_layout.addLayout(mapping_header)

        self.mapping_detail_label = QLabel("请先加载文件，然后为每个逻辑通道设置脑区。")
        self.mapping_detail_label.setProperty("role", "caption")
        self.mapping_detail_label.setWordWrap(True)
        mapping_header.addWidget(self.mapping_detail_label, 1)

        self.edit_mapping_button = QPushButton("编辑映射")
        self.edit_mapping_button.setProperty("variant", "secondary")
        self.edit_mapping_button.clicked.connect(self._open_region_mapping_dialog)
        self.edit_mapping_button.setEnabled(False)
        mapping_header.addWidget(self.edit_mapping_button)

        self.mapping_table = QTableWidget(0, 6)
        self.mapping_table.setHorizontalHeaderLabels(["Channel ID", "Subject", "Region", "LFP Count", "Unit Count", "Sources"])
        self.mapping_table.horizontalHeader().setStretchLastSection(True)
        mapping_layout.addWidget(self.mapping_table, 1)
        content_splitter.addWidget(mapping_group)
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 4)

        batch_group = QGroupBox("批量分析")
        layout.addWidget(batch_group)
        batch_layout = QGridLayout(batch_group)
        batch_layout.setHorizontalSpacing(12)
        batch_layout.setVerticalSpacing(12)

        self.batch_input_edit = QLineEdit(self.profile.input_defaults.get("batch_input_dir", ""))
        self.batch_input_edit.setPlaceholderText("选择包含 .nex5 文件的输入目录")
        self.batch_input_edit.textChanged.connect(self._refresh_batch_run_enabled)
        batch_layout.addWidget(QLabel("输入目录"), 0, 0)
        batch_layout.addWidget(self.batch_input_edit, 0, 1)
        browse_batch_input_button = QPushButton("浏览")
        browse_batch_input_button.setProperty("variant", "secondary")
        browse_batch_input_button.clicked.connect(self._choose_batch_input_dir)
        batch_layout.addWidget(browse_batch_input_button, 0, 2)

        self.batch_output_edit = QLineEdit(self.profile.input_defaults.get("batch_output_dir", ""))
        self.batch_output_edit.setPlaceholderText("选择批量结果输出目录")
        self.batch_output_edit.textChanged.connect(self._refresh_batch_run_enabled)
        batch_layout.addWidget(QLabel("输出目录"), 1, 0)
        batch_layout.addWidget(self.batch_output_edit, 1, 1)
        browse_batch_output_button = QPushButton("浏览")
        browse_batch_output_button.setProperty("variant", "secondary")
        browse_batch_output_button.clicked.connect(self._choose_batch_output_dir)
        batch_layout.addWidget(browse_batch_output_button, 1, 2)

        self.batch_config_edit = QLineEdit()
        self.batch_config_edit.setReadOnly(True)
        batch_layout.addWidget(QLabel("当前配置"), 2, 0)
        batch_layout.addWidget(self.batch_config_edit, 2, 1, 1, 2)

        batch_selection_group = QGroupBox("批量分析项")
        batch_selection_layout = QGridLayout(batch_selection_group)
        batch_selection_layout.setHorizontalSpacing(10)
        batch_selection_layout.setVerticalSpacing(10)
        self._build_batch_analysis_picker(batch_selection_layout)
        batch_layout.addWidget(batch_selection_group, 3, 0, 1, 3)

        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setRange(0, 100)
        self.batch_progress_bar.setValue(0)
        batch_layout.addWidget(self.batch_progress_bar, 4, 0, 1, 3)

        self.batch_run_button = QPushButton("运行批量分析")
        self.batch_run_button.clicked.connect(self._run_batch_analysis)
        batch_layout.addWidget(self.batch_run_button, 5, 0, 1, 3)

        self.batch_status_view = QTextEdit()
        self.batch_status_view.setReadOnly(True)
        self.batch_status_view.setPlaceholderText("批量状态、进度和结果汇总会显示在这里。")
        self.batch_status_view.setMinimumHeight(120)
        batch_layout.addWidget(self.batch_status_view, 6, 0, 1, 3)

        self._update_batch_profile_display()
        self._apply_batch_defaults_from_profile()
        self._refresh_header_status()
        self._refresh_mapping_state()
        self._refresh_batch_run_enabled()

    def _build_batch_analysis_picker(self, layout: QGridLayout) -> None:
        scope_labels = {
            "lfp": "LFP",
            "spike": "Spike",
            "lfp_lfp": "LFP-LFP",
            "spike_lfp": "Spike-LFP",
        }
        for index, definition in enumerate(iter_analysis_definitions()):
            checkbox = QCheckBox(f"[{scope_labels[definition.scope]}] {definition.label}")
            checkbox.setToolTip(definition.key)
            checkbox.toggled.connect(self._refresh_batch_run_enabled)
            layout.addWidget(checkbox, index // 2, index % 2)
            self.batch_analysis_checkboxes[definition.key] = checkbox

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 NEX5 文件", str(Path.cwd()), "NEX5 Files (*.nex5)")
        if path:
            self.load_session(Path(path))

    def _choose_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择配置文件", str(Path.cwd()), "JSON Files (*.json)")
        if not path:
            return
        self.profile = SessionProfile.load_json(Path(path))
        self.current_profile_path = Path(path)
        self._persist_profile_state()
        self._update_batch_profile_display()
        self._apply_batch_defaults_from_profile()
        if self.current_file_path:
            self.load_session(self.current_file_path)
        else:
            self._refresh_header_status()
            self._refresh_mapping_state()

    def _save_profile(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存配置",
            str(Path.cwd() / "session_profile.json"),
            "JSON Files (*.json)",
        )
        if not path:
            return
        self.profile.input_defaults["batch_input_dir"] = self.batch_input_edit.text().strip()
        self.profile.input_defaults["batch_output_dir"] = self.batch_output_edit.text().strip()
        self.profile.input_defaults["batch_analysis_keys"] = sorted(self._selected_batch_analysis_keys())
        self.profile.save_json(Path(path))
        self.current_profile_path = Path(path)
        self._persist_profile_state()
        self._update_batch_profile_display()
        self._refresh_header_status()

    def load_session(self, file_path: Path) -> None:
        self.current_file_path = file_path
        self.session = self.loader.inspect(
            file_path,
            manual_channel_ids=self.profile.input_defaults.get("manual_channel_ids", {}),
            region_map=self.profile.channel_region_map,
        )
        self._populate_metadata()
        self._populate_mapping_table()
        self._refresh_header_status()
        self._refresh_mapping_state()

    def _populate_metadata(self) -> None:
        if self.session is None:
            self.metadata_view.clear()
            return
        lines = [
            f"文件名：{self.session.file_name}",
            f"记录时长：{self.session.metadata['duration_s']:.3f} s",
            f"时间戳频率：{self.session.metadata['timestamp_frequency_hz']:.3f} Hz",
            f"LFP 通道数：{len(self.session.lfp_channels)}",
            f"Spike 单元数：{len(self.session.spike_units)}",
            f"包含波形：{'是' if self.session.waveform_available else '否'}",
            f"识别到的逻辑通道：{', '.join(f'CH{channel:02d}' for channel in self.session.channel_ids) or '无'}",
        ]
        self.metadata_view.setPlainText("\n".join(lines))

    def _populate_mapping_table(self) -> None:
        if self.session is None:
            self.mapping_table.setRowCount(0)
            return
        rows = self._build_mapping_rows()
        self.mapping_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            channel_item = QTableWidgetItem("" if row["channel_id"] is None else str(row["channel_id"]))
            subject_item = QTableWidgetItem(row["subject"])
            region_item = QTableWidgetItem(row["region"])
            lfp_item = QTableWidgetItem(str(row["lfp_count"]))
            unit_item = QTableWidgetItem(str(row["unit_count"]))
            source_item = QTableWidgetItem(", ".join(row["sources"]))
            for item in (channel_item, subject_item, region_item, lfp_item, unit_item, source_item):
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.mapping_table.setItem(row_index, 0, channel_item)
            self.mapping_table.setItem(row_index, 1, subject_item)
            self.mapping_table.setItem(row_index, 2, region_item)
            self.mapping_table.setItem(row_index, 3, lfp_item)
            self.mapping_table.setItem(row_index, 4, unit_item)
            self.mapping_table.setItem(row_index, 5, source_item)
        self.mapping_table.resizeColumnsToContents()

    def _build_mapping_rows(self) -> list[dict]:
        assert self.session is not None
        grouped = defaultdict(
            lambda: {"channel_id": None, "subject": "", "region": "", "lfp_count": 0, "unit_count": 0, "sources": []}
        )
        for channel in self.session.lfp_channels:
            key = channel.channel_id if channel.channel_id is not None else f"unresolved:{channel.variable_name}"
            grouped[key]["channel_id"] = channel.channel_id
            grouped[key]["subject"] = channel.subject or grouped[key]["subject"]
            grouped[key]["region"] = channel.region or grouped[key]["region"] or "Unknown"
            grouped[key]["lfp_count"] += 1
            grouped[key]["sources"].append(channel.variable_name)
        for unit in self.session.spike_units:
            key = unit.channel_id if unit.channel_id is not None else f"unresolved:{unit.variable_name}"
            grouped[key]["channel_id"] = unit.channel_id
            grouped[key]["subject"] = unit.subject or grouped[key]["subject"]
            grouped[key]["region"] = unit.region or grouped[key]["region"] or "Unknown"
            grouped[key]["unit_count"] += 1
            grouped[key]["sources"].append(unit.variable_name)
        rows = list(grouped.values())
        rows.sort(key=lambda row: (row["channel_id"] is None, row["channel_id"] if row["channel_id"] is not None else 10**9, row["sources"][0]))
        return rows

    def _open_region_mapping_dialog(self) -> None:
        if self.session is None:
            QMessageBox.information(self, "脑区映射", "请先加载一个 NEX5 文件。")
            return
        dialog = ChannelRegionMappingDialog(self.session.channel_ids, self.profile.channel_region_map, self)
        if dialog.exec():
            self._apply_region_map(dialog.result_region_map)

    def _apply_region_map(self, region_map: RegionMapping) -> None:
        self.profile.channel_region_map = dict(region_map)
        self._persist_profile_state()
        if self.current_file_path is not None:
            self.load_session(self.current_file_path)
        else:
            self._refresh_header_status()
            self._refresh_mapping_state()

    def _restore_persisted_profile_state(self) -> None:
        if not self.autosave_profile_path.exists():
            return
        try:
            payload = json.loads(self.autosave_profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        profile_payload = payload.get("profile") if isinstance(payload, dict) and "profile" in payload else payload
        if not isinstance(profile_payload, dict):
            return

        try:
            self.profile = SessionProfile.from_dict(profile_payload)
        except (TypeError, ValueError):
            self.profile = SessionProfile.default()
            return

        current_profile_path = payload.get("current_profile_path") if isinstance(payload, dict) else None
        if current_profile_path:
            self.current_profile_path = Path(current_profile_path)

    def _persist_profile_state(self) -> None:
        payload = {
            "current_profile_path": None if self.current_profile_path is None else str(self.current_profile_path),
            "profile": self.profile.to_dict(),
        }
        self.autosave_profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.autosave_profile_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _region_mapping_errors(self) -> list[str]:
        if self.session is None:
            return ["请先加载一个 NEX5 文件。"]
        return validate_region_map(self.profile.channel_region_map, self.session.channel_ids)

    def _has_complete_region_mapping(self) -> bool:
        return not self._region_mapping_errors()

    def _ensure_complete_region_mapping(self) -> bool:
        errors = self._region_mapping_errors()
        if not errors:
            return True
        QMessageBox.warning(
            self,
            "脑区映射未完成",
            "必须为当前文件的每个逻辑通道设置脑区后才能继续。\n\n" + "\n".join(errors),
        )
        self._open_region_mapping_dialog()
        return self._has_complete_region_mapping()

    def _refresh_header_status(self) -> None:
        if self.current_file_path is None:
            self.file_status_label.setText("文件：未加载")
            set_status_tone(self.file_status_label, "info")
        else:
            self.file_status_label.setText(f"文件：{self.current_file_path.name}")
            set_status_tone(self.file_status_label, "ok")

        if self.current_profile_path is None:
            self.profile_status_label.setText("配置：内存配置")
            set_status_tone(self.profile_status_label, "info")
        else:
            self.profile_status_label.setText(f"配置：{self.current_profile_path.name}")
            set_status_tone(self.profile_status_label, "ok")

        if self.session is None:
            self.mapping_status_label.setText("映射：等待加载文件")
            set_status_tone(self.mapping_status_label, "warn")
            return

        total_channels = len(self.session.channel_ids)
        mapped_channels = sum(
            1
            for channel_id in self.session.channel_ids
            if normalize_region_assignment(self.profile.channel_region_map.get(channel_id)) is not None
        )
        if mapped_channels == total_channels and total_channels > 0:
            self.mapping_status_label.setText(f"映射：已完成 {mapped_channels}/{total_channels}")
            set_status_tone(self.mapping_status_label, "ok")
        else:
            self.mapping_status_label.setText(f"映射：待完成 {mapped_channels}/{total_channels}")
            set_status_tone(self.mapping_status_label, "warn")

    def _refresh_mapping_state(self) -> None:
        has_session = self.session is not None
        self.edit_mapping_button.setEnabled(has_session)
        if not has_session:
            self.mapping_detail_label.setText("请先加载文件，然后为每个逻辑通道设置脑区。")
            self.open_workspace_button.setEnabled(False)
            self._refresh_batch_run_enabled()
            return

        errors = self._region_mapping_errors()
        if errors:
            self.mapping_detail_label.setText(
                "当前映射还不完整。请打开映射窗口，确保每个逻辑通道都被分配到脑区。"
            )
            self.open_workspace_button.setEnabled(False)
        else:
            self.mapping_detail_label.setText(
                "当前样本的脑区映射已完成，可以进入分析工作台或执行批量分析。"
            )
            self.open_workspace_button.setEnabled(True)
        self._refresh_batch_run_enabled()

    def _open_workspace(self) -> None:
        if self.session is None or self.current_file_path is None:
            QMessageBox.information(self, "分析工作台", "请先加载一个 NEX5 文件。")
            return
        if not self._ensure_complete_region_mapping():
            return
        dialog = AnalysisWorkspaceDialog(self.session, self.profile, self)
        dialog.exec()

    def _open_grouped_plv_workspace(self) -> None:
        initial_entries: list[GroupedPLVManifestEntry] = []
        if self.current_file_path is not None:
            subject = self.current_file_path.stem
            region = None
            if self.session is not None and len(self.session.subject_names) == 1:
                subject = self.session.subject_names[0]
            if self.session is not None:
                region_values = {
                    str(region_value).strip()
                    for region_value in [
                        *(channel.region for channel in self.session.lfp_channels),
                        *(unit.region for unit in self.session.spike_units),
                    ]
                    if str(region_value or "").strip()
                }
                if len(region_values) == 1:
                    region = next(iter(region_values))
            initial_entries.append(
                GroupedPLVManifestEntry(
                    file_path=self.current_file_path,
                    group="第 1 组",
                    subject=subject,
                    region=region,
                )
            )
        dialog = GroupedPLVWorkspaceDialog(self.profile, self, initial_entries=initial_entries)
        dialog.exec()

    def _choose_batch_input_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "选择批量输入目录",
            self.batch_input_edit.text().strip() or str(Path.cwd()),
        )
        if path:
            self.batch_input_edit.setText(path)

    def _choose_batch_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "选择批量输出目录",
            self.batch_output_edit.text().strip() or str(Path.cwd()),
        )
        if path:
            self.batch_output_edit.setText(path)

    def _refresh_batch_run_enabled(self) -> None:
        has_input = bool(self.batch_input_edit.text().strip())
        has_output = bool(self.batch_output_edit.text().strip())
        has_selection = bool(self._selected_batch_analysis_keys())
        has_session = self.session is not None
        has_mapping = self._has_complete_region_mapping() if has_session else False
        self.batch_run_button.setEnabled(has_input and has_output and has_selection and has_session and has_mapping)

    def _apply_batch_defaults_from_profile(self) -> None:
        self.batch_input_edit.setText(self.profile.input_defaults.get("batch_input_dir", ""))
        self.batch_output_edit.setText(self.profile.input_defaults.get("batch_output_dir", ""))
        self._apply_batch_analysis_selection_from_profile()
        self.batch_progress_bar.setValue(0)
        self._refresh_batch_run_enabled()

    def _default_batch_analysis_selection(self) -> set[str]:
        return {
            definition.key
            for definition in iter_analysis_definitions()
            if self.profile.enabled_analyses.get(definition.key, True)
        }

    def _apply_batch_analysis_selection_from_profile(self) -> None:
        if "batch_analysis_keys" in self.profile.input_defaults:
            raw_selected = [str(key) for key in self.profile.input_defaults.get("batch_analysis_keys", [])]
            selected = {
                key
                for key in raw_selected
                if key in self.batch_analysis_checkboxes
            }
            if raw_selected and not selected:
                selected = self._default_batch_analysis_selection()
        else:
            selected = self._default_batch_analysis_selection()
        for key, checkbox in self.batch_analysis_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(key in selected)
            checkbox.blockSignals(False)

    def _selected_batch_analysis_keys(self) -> set[str]:
        return {key for key, checkbox in self.batch_analysis_checkboxes.items() if checkbox.isChecked()}

    def _update_batch_profile_display(self) -> None:
        if self.current_profile_path is not None:
            self.batch_config_edit.setText(str(self.current_profile_path))
        else:
            self.batch_config_edit.setText("当前使用内存配置（尚未单独保存）")

    def _run_batch_analysis(self) -> None:
        input_dir = Path(self.batch_input_edit.text().strip())
        output_dir = Path(self.batch_output_edit.text().strip())
        analysis_keys = self._selected_batch_analysis_keys()

        if self.session is None:
            QMessageBox.warning(self, "批量分析", "请先加载一个样本并完成脑区映射。")
            return
        if not self._ensure_complete_region_mapping():
            return
        if not input_dir.exists() or not input_dir.is_dir():
            QMessageBox.warning(self, "批量分析", "请输入有效的批量输入目录。")
            return
        if not any(input_dir.glob("*.nex5")):
            QMessageBox.warning(self, "批量分析", "输入目录中没有找到 .nex5 文件。")
            return
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.warning(self, "批量分析", f"无法创建输出目录：{exc}")
                return
        if not output_dir.is_dir():
            QMessageBox.warning(self, "批量分析", "输出路径不是目录。")
            return
        if not analysis_keys:
            QMessageBox.warning(self, "批量分析", "请至少选择一个批量分析项。")
            return

        self.profile.input_defaults["batch_input_dir"] = str(input_dir)
        self.profile.input_defaults["batch_output_dir"] = str(output_dir)
        self.profile.input_defaults["batch_analysis_keys"] = sorted(analysis_keys)
        self.batch_run_button.setEnabled(False)
        self.batch_progress_bar.setValue(0)
        self.batch_status_view.setPlainText("批量分析运行中，请稍候…")

        batch_profile = self.profile.clone()
        batch_profile.input_defaults["batch_input_dir"] = str(input_dir)
        batch_profile.input_defaults["batch_output_dir"] = str(output_dir)
        batch_profile.input_defaults["batch_analysis_keys"] = sorted(analysis_keys)

        worker = TaskWorker(
            self._execute_batch_run,
            input_dir,
            output_dir,
            analysis_keys=analysis_keys,
            profile_snapshot=batch_profile,
            reference_channel_ids=list(self.session.channel_ids),
            inject_progress=True,
        )
        worker.signals.progress.connect(self._on_batch_progress)
        worker.signals.result.connect(self._on_batch_run_success)
        worker.signals.error.connect(self._on_batch_run_error)
        worker.signals.finished.connect(self._on_batch_run_finished)
        self.batch_thread_pool.start(worker)

    def _execute_batch_run(
        self,
        input_dir: Path,
        output_dir: Path,
        analysis_keys: set[str] | None = None,
        profile_snapshot: SessionProfile | None = None,
        reference_channel_ids: list[int] | None = None,
        progress_callback=None,
    ) -> BatchRunReport:
        selected_analysis_keys = set(analysis_keys or self._selected_batch_analysis_keys())
        batch_profile = profile_snapshot.clone() if profile_snapshot is not None else self.profile.clone()
        batch_profile.input_defaults["batch_input_dir"] = str(input_dir)
        batch_profile.input_defaults["batch_output_dir"] = str(output_dir)
        batch_profile.input_defaults["batch_analysis_keys"] = sorted(selected_analysis_keys)
        return self.batch_runner.run_directory(
            input_dir,
            output_dir,
            batch_profile,
            analysis_keys=selected_analysis_keys,
            reference_channel_ids=reference_channel_ids,
            progress_callback=progress_callback,
        )

    def _on_batch_progress(self, update: BatchProgressUpdate) -> None:
        self.batch_progress_bar.setValue(update.progress_percent)
        lines = [
            f"阶段：{self._phase_label(update.phase)}",
            f"进度：{update.completed_files} / {update.total_files}",
            f"成功任务：{update.success_count}",
            f"失败任务：{update.failure_count}",
        ]
        if update.current_file is not None:
            lines.append(f"当前文件：{update.current_file.name}")
        if update.message:
            lines.append(f"说明：{update.message}")
        self.batch_status_view.setPlainText("\n".join(lines))

    def _on_batch_run_success(self, report: BatchRunReport) -> None:
        self.batch_progress_bar.setValue(100)
        lines = [
            "批量分析已完成。",
            f"成功任务：{report.success_count}",
            f"失败任务：{report.failure_count}",
            f"成功汇总：{report.run_summary_path}",
            f"失败汇总：{report.failures_path}",
        ]
        self.batch_status_view.setPlainText("\n".join(lines))
        self.batch_run_button.setEnabled(True)

    def _on_batch_run_error(self, message: str) -> None:
        self.batch_status_view.setPlainText(f"批量分析失败：{message}")
        QMessageBox.critical(self, "批量分析失败", message)

    def _on_batch_run_finished(self) -> None:
        self._refresh_batch_run_enabled()

    @staticmethod
    def _phase_label(phase: str) -> str:
        labels = {
            "starting": "准备中",
            "loading": "处理中",
            "completed": "单文件完成",
            "finished": "全部完成",
        }
        return labels.get(phase, phase)
