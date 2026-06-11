from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..analysis.registry import get_analysis_definition
from ..defaults import PARAMETER_SPECS


class ParameterPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(12)

        self.title_label = QLabel("参数设置")
        self.title_label.setProperty("role", "section-title")
        outer_layout.addWidget(self.title_label)

        self.info_label = QLabel("选择一个具体分析节点后，在这里调整参数。")
        self.info_label.setWordWrap(True)
        self.info_label.setProperty("role", "caption")
        outer_layout.addWidget(self.info_label)

        self.scope_hint_label = QLabel("参数会同步应用到这一类分析。")
        self.scope_hint_label.setWordWrap(True)
        self.scope_hint_label.setProperty("role", "muted")
        outer_layout.addWidget(self.scope_hint_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer_layout.addWidget(self.scroll, 1)

        self.form_host = QWidget()
        self.form_layout = QFormLayout(self.form_host)
        self.form_layout.setContentsMargins(8, 8, 8, 8)
        self.form_layout.setLabelAlignment(Qt.AlignLeft)
        self.form_layout.setHorizontalSpacing(14)
        self.form_layout.setVerticalSpacing(12)
        self.scroll.setWidget(self.form_host)

        self._widgets: dict[str, QWidget] = {}

    def set_analysis(self, analysis_key: str | None, values: dict) -> None:
        while self.form_layout.rowCount():
            self.form_layout.removeRow(0)
        self._widgets.clear()

        if not analysis_key:
            self.title_label.setText("参数设置")
            self.info_label.setText("选择一个具体分析节点后，在这里调整参数。")
            self.scope_hint_label.setText("参数会同步应用到这一类分析。")
            return

        definition = get_analysis_definition(analysis_key)
        self.title_label.setText(definition.label)
        self.scope_hint_label.setText(f"当前修改会同步到所有“{definition.label}”结果。")

        specs = PARAMETER_SPECS.get(analysis_key, [])
        if not specs:
            self.info_label.setText("这个分析在当前版本没有可编辑参数。")
            return

        self.info_label.setText("调整参数后，点击下方按钮应用到这一类分析。")
        for spec in specs:
            widget = self._make_widget(
                spec.kind,
                values.get(spec.key),
                spec.minimum,
                spec.maximum,
                spec.step,
                spec.choices,
            )
            self._widgets[spec.key] = widget
            self.form_layout.addRow(spec.label, widget)
        self._bind_toggle_dependencies("plot_use_custom_x_range", ("plot_x_min", "plot_x_max"))
        self._bind_toggle_dependencies("plot_use_custom_y_range", ("plot_y_min", "plot_y_max"))
        self._bind_toggle_dependencies("plot_use_custom_color_range", ("plot_color_min", "plot_color_max"))

    def values(self) -> dict:
        result = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, QDoubleSpinBox):
                result[key] = float(widget.value())
            elif isinstance(widget, QSpinBox):
                result[key] = int(widget.value())
            elif isinstance(widget, QCheckBox):
                result[key] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                result[key] = widget.currentData() or widget.currentText()
        return result

    def apply_values(self, values: dict) -> None:
        for key, value in values.items():
            widget = self._widgets.get(key)
            if widget is None:
                continue
            if isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                index = widget.findData(value)
                if index < 0:
                    index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)

    def _make_widget(self, kind: str, value, minimum, maximum, step, choices: tuple[str, ...] | None) -> QWidget:
        if kind == "int":
            widget = QSpinBox()
            widget.setRange(int(minimum or -10_000_000), int(maximum or 10_000_000))
            widget.setSingleStep(int(step or 1))
            widget.setValue(int(value if value is not None else minimum or 0))
            return widget
        if kind == "float":
            widget = QDoubleSpinBox()
            widget.setDecimals(4)
            widget.setRange(float(minimum or -10_000_000.0), float(maximum or 10_000_000.0))
            widget.setSingleStep(float(step or 0.1))
            widget.setValue(float(value if value is not None else minimum or 0.0))
            return widget
        if kind == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(value))
            return widget
        if kind == "choice":
            widget = QComboBox()
            for choice in choices or ():
                widget.addItem(choice, choice)
            if widget.count() == 0 and value is not None:
                widget.addItem(str(value), str(value))
            current_value = value if value is not None else widget.currentData()
            index = widget.findData(current_value)
            if index < 0:
                index = widget.findText(str(current_value))
            if index >= 0:
                widget.setCurrentIndex(index)
            return widget
        fallback = QDoubleSpinBox()
        fallback.setValue(float(value if value is not None else minimum or 0.0))
        return fallback

    def _bind_toggle_dependencies(self, controller_key: str, dependent_keys: tuple[str, ...]) -> None:
        controller = self._widgets.get(controller_key)
        if not isinstance(controller, QCheckBox):
            return

        def sync_state(checked: bool) -> None:
            for dependent_key in dependent_keys:
                widget = self._widgets.get(dependent_key)
                if widget is not None:
                    widget.setEnabled(checked)

        controller.toggled.connect(sync_state)
        sync_state(controller.isChecked())
