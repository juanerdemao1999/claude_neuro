from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..models import (
    RegionAssignment,
    RegionMapping,
    normalize_region_assignment,
    normalize_region_map,
    serialize_region_assignment,
)
from .theme import ensure_app_theme, set_status_tone


@dataclass(frozen=True, slots=True)
class RegionMappingEntry:
    channel_range: str
    region: str
    subject: str = ""


def parse_channel_range(value: str) -> tuple[int, int]:
    normalized = value.strip().replace(" ", "")
    if not normalized:
        raise ValueError("通道范围不能为空。")
    if "-" in normalized:
        parts = normalized.split("-")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("通道范围格式应为 1-4 或单个编号。")
        start_channel, end_channel = (int(part) for part in parts)
    else:
        if not normalized.isdigit():
            raise ValueError("通道范围格式应为 1-4 或单个编号。")
        start_channel = end_channel = int(normalized)
    if start_channel <= 0 or end_channel <= 0:
        raise ValueError("通道编号必须大于 0。")
    if start_channel > end_channel:
        raise ValueError("通道范围起始值不能大于结束值。")
    return start_channel, end_channel


def build_region_map_from_entries(
    entries: list[RegionMappingEntry],
    channel_ids: list[int],
) -> RegionMapping:
    expected_channels = sorted({int(channel_id) for channel_id in channel_ids})
    errors: list[str] = []
    region_map: RegionMapping = {}

    for index, entry in enumerate(entries, start=1):
        channel_range = entry.channel_range.strip()
        subject = entry.subject.strip()
        region = entry.region.strip()
        if not channel_range and not subject and not region:
            continue
        if not channel_range:
            errors.append(f"第 {index} 行缺少通道范围。")
            continue
        if not region:
            errors.append(f"第 {index} 行缺少脑区名称。")
            continue
        try:
            start_channel, end_channel = parse_channel_range(channel_range)
        except ValueError as exc:
            errors.append(f"第 {index} 行：{exc}")
            continue

        mapping_value = serialize_region_assignment({"subject": subject, "region": region})
        assert mapping_value is not None
        for channel_id in range(start_channel, end_channel + 1):
            if channel_id not in expected_channels:
                errors.append(f"第 {index} 行包含不存在的通道 {channel_id}。")
                continue
            if channel_id in region_map:
                errors.append(f"通道 {channel_id} 被重复设置脑区。")
                continue
            region_map[channel_id] = mapping_value

    missing_channels = [channel_id for channel_id in expected_channels if channel_id not in region_map]
    if missing_channels:
        errors.append("以下通道尚未设置脑区：" + ", ".join(str(channel_id) for channel_id in missing_channels))

    if errors:
        raise ValueError("\n".join(errors))
    return region_map


def validate_region_map(region_map: RegionMapping, channel_ids: list[int]) -> list[str]:
    normalized = normalize_region_map(region_map)
    expected_channels = sorted({int(channel_id) for channel_id in channel_ids})
    missing_channels = [
        channel_id
        for channel_id in expected_channels
        if normalize_region_assignment(normalized.get(channel_id)) is None
    ]
    if missing_channels:
        return ["以下通道尚未设置脑区：" + ", ".join(str(channel_id) for channel_id in missing_channels)]
    return []


def compress_region_map(channel_ids: list[int], region_map: RegionMapping) -> list[RegionMappingEntry]:
    normalized = normalize_region_map(region_map)
    ordered_channels = sorted({int(channel_id) for channel_id in channel_ids})
    if not ordered_channels:
        return []

    entries: list[RegionMappingEntry] = []
    start_channel: int | None = None
    previous_channel: int | None = None
    current_assignment: RegionAssignment | None = None

    for channel_id in ordered_channels:
        assignment = normalize_region_assignment(normalized.get(channel_id))
        if assignment is None:
            continue
        if start_channel is None:
            start_channel = previous_channel = channel_id
            current_assignment = assignment
            continue
        if previous_channel is not None and channel_id == previous_channel + 1 and assignment == current_assignment:
            previous_channel = channel_id
            continue
        assert previous_channel is not None
        assert current_assignment is not None
        entries.append(_entry_from_assignment(start_channel, previous_channel, current_assignment))
        start_channel = previous_channel = channel_id
        current_assignment = assignment

    if start_channel is not None and previous_channel is not None and current_assignment is not None:
        entries.append(_entry_from_assignment(start_channel, previous_channel, current_assignment))
    return entries


def _entry_from_assignment(start_channel: int, end_channel: int, assignment: RegionAssignment) -> RegionMappingEntry:
    return RegionMappingEntry(
        channel_range=_format_channel_range(start_channel, end_channel),
        subject=assignment.subject or "",
        region=assignment.region,
    )


def _format_channel_range(start_channel: int, end_channel: int) -> str:
    if start_channel == end_channel:
        return str(start_channel)
    return f"{start_channel}-{end_channel}"


class ChannelRegionMappingDialog(QDialog):
    def __init__(
        self,
        channel_ids: list[int],
        current_region_map: RegionMapping | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        ensure_app_theme()

        self.channel_ids = sorted({int(channel_id) for channel_id in channel_ids})
        self.current_region_map = normalize_region_map(current_region_map or {})
        self.result_region_map: RegionMapping = {}

        self.setWindowTitle("脑区通道映射")
        self.resize(820, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title_label = QLabel("设置脑区映射")
        title_label.setProperty("role", "hero-title")
        layout.addWidget(title_label)

        hint_label = QLabel(
            "每一行填写一个逻辑通道范围对应的鼠名和脑区。"
            "如果是双鼠实验，可以先给两只鼠分别起名，再把选中行批量套用过去。"
        )
        hint_label.setWordWrap(True)
        hint_label.setProperty("role", "caption")
        layout.addWidget(hint_label)

        channel_text = ", ".join(str(channel_id) for channel_id in self.channel_ids)
        self.channel_summary_label = QLabel(f"当前文件逻辑通道：{channel_text}")
        self.channel_summary_label.setProperty("role", "muted")
        self.channel_summary_label.setWordWrap(True)
        layout.addWidget(self.channel_summary_label)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        layout.addLayout(preset_row)

        preset_row.addWidget(QLabel("鼠 1 名称"))
        self.mouse_one_name_edit = QLineEdit()
        self.mouse_one_name_edit.setPlaceholderText("例如：Alpha")
        preset_row.addWidget(self.mouse_one_name_edit, 1)
        mouse_one_button = QPushButton("选中行设为鼠 1")
        mouse_one_button.setProperty("variant", "secondary")
        mouse_one_button.clicked.connect(lambda: self._apply_subject_preset(self.mouse_one_name_edit.text()))
        preset_row.addWidget(mouse_one_button)

        preset_row.addWidget(QLabel("鼠 2 名称"))
        self.mouse_two_name_edit = QLineEdit()
        self.mouse_two_name_edit.setPlaceholderText("例如：Beta")
        preset_row.addWidget(self.mouse_two_name_edit, 1)
        mouse_two_button = QPushButton("选中行设为鼠 2")
        mouse_two_button.setProperty("variant", "secondary")
        mouse_two_button.clicked.connect(lambda: self._apply_subject_preset(self.mouse_two_name_edit.text()))
        preset_row.addWidget(mouse_two_button)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["通道范围", "鼠名/主体", "脑区"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._update_coverage_status)
        layout.addWidget(self.table, 1)

        tool_row = QHBoxLayout()
        add_row_button = QPushButton("新增一行")
        add_row_button.setProperty("variant", "secondary")
        add_row_button.clicked.connect(self._add_empty_row)
        tool_row.addWidget(add_row_button)

        remove_row_button = QPushButton("删除选中行")
        remove_row_button.setProperty("variant", "secondary")
        remove_row_button.clicked.connect(self._remove_selected_rows)
        tool_row.addWidget(remove_row_button)
        tool_row.addStretch(1)
        layout.addLayout(tool_row)

        self.coverage_label = QLabel()
        self.coverage_label.setProperty("role", "status")
        layout.addWidget(self.coverage_label)

        action_row = QHBoxLayout()
        action_row.addStretch(1)

        cancel_button = QPushButton("取消")
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)
        action_row.addWidget(cancel_button)

        save_button = QPushButton("保存映射")
        save_button.clicked.connect(self._save_mapping)
        action_row.addWidget(save_button)
        layout.addLayout(action_row)

        self._load_existing_entries()
        self._update_subject_presets_from_map()
        self._update_coverage_status()

    def _load_existing_entries(self) -> None:
        entries = compress_region_map(self.channel_ids, self.current_region_map)
        if not entries:
            entries = [RegionMappingEntry(channel_range="", subject="", region="")]
        self.table.blockSignals(True)
        for entry in entries:
            self._append_row(entry.channel_range, entry.subject, entry.region)
        self.table.blockSignals(False)

    def _append_row(self, channel_range: str, subject: str, region: str) -> None:
        row_index = self.table.rowCount()
        self.table.insertRow(row_index)
        self.table.setItem(row_index, 0, QTableWidgetItem(channel_range))
        self.table.setItem(row_index, 1, QTableWidgetItem(subject))
        self.table.setItem(row_index, 2, QTableWidgetItem(region))

    def _add_empty_row(self) -> None:
        self._append_row("", "", "")
        self._update_coverage_status()

    def _remove_selected_rows(self) -> None:
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not selected_rows:
            return
        self.table.blockSignals(True)
        for row_index in selected_rows:
            self.table.removeRow(row_index)
        if self.table.rowCount() == 0:
            self._append_row("", "", "")
        self.table.blockSignals(False)
        self._update_coverage_status()

    def _collect_entries(self) -> list[RegionMappingEntry]:
        entries: list[RegionMappingEntry] = []
        for row_index in range(self.table.rowCount()):
            range_item = self.table.item(row_index, 0)
            subject_item = self.table.item(row_index, 1)
            region_item = self.table.item(row_index, 2)
            entries.append(
                RegionMappingEntry(
                    channel_range="" if range_item is None else range_item.text(),
                    subject="" if subject_item is None else subject_item.text(),
                    region="" if region_item is None else region_item.text(),
                )
            )
        return entries

    def _update_subject_presets_from_map(self) -> None:
        subjects = sorted(
            {
                assignment.subject or ""
                for assignment in (
                    normalize_region_assignment(value) for value in self.current_region_map.values()
                )
                if assignment is not None and assignment.subject
            }
        )
        if subjects:
            self.mouse_one_name_edit.setText(subjects[0])
        if len(subjects) > 1:
            self.mouse_two_name_edit.setText(subjects[1])

    def _apply_subject_preset(self, subject_name: str) -> None:
        subject = subject_name.strip()
        if not subject:
            QMessageBox.information(self, "鼠名未填写", "请先输入鼠的名称，再把它应用到选中行。")
            return
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not selected_rows:
            QMessageBox.information(self, "未选择行", "请先选中要应用这个鼠名的映射行。")
            return
        self.table.blockSignals(True)
        for row_index in selected_rows:
            item = self.table.item(row_index, 1)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row_index, 1, item)
            item.setText(subject)
        self.table.blockSignals(False)
        self._update_coverage_status()

    def _update_coverage_status(self) -> None:
        try:
            region_map = build_region_map_from_entries(self._collect_entries(), self.channel_ids)
        except ValueError as exc:
            errors = [line.strip() for line in str(exc).splitlines() if line.strip()]
            first_error = errors[0] if errors else "映射尚未完成。"
            self.coverage_label.setText(f"待完成：{first_error}")
            set_status_tone(self.coverage_label, "warn")
            return

        self.coverage_label.setText(f"映射已完成：{len(region_map)} / {len(self.channel_ids)} 个通道已设置。")
        set_status_tone(self.coverage_label, "ok")

    def _save_mapping(self) -> None:
        try:
            self.result_region_map = build_region_map_from_entries(self._collect_entries(), self.channel_ids)
        except ValueError as exc:
            QMessageBox.warning(self, "脑区映射不完整", str(exc))
            self._update_coverage_status()
            return
        self.accept()
