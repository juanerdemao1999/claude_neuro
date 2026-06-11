from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

from ..models import AnalysisResult
from ..plotting import create_publication_figure, render_result_figure


class PreviewWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.title_label = QLabel("结果预览")
        self.title_label.setProperty("role", "section-title")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("选择一个分析节点后，这里会显示图形和数据预览。")
        self.subtitle_label.setProperty("role", "caption")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)

        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack, 1)

        self.message_label = QLabel("请选择一个分析节点以查看结果。")
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setProperty("role", "caption")
        self.message_label.setStyleSheet("padding: 24px;")
        self.stack.addWidget(self.message_label)

        figure = create_publication_figure(
            AnalysisResult(
                node_id="preview:empty",
                title="预览",
                kind="message",
                message="请选择一个分析节点以查看结果。",
            )
        )
        self.canvas = FigureCanvasQTAgg(figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        self.plot_host = QWidget()
        plot_layout = QVBoxLayout(self.plot_host)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(8)
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas)
        self.stack.addWidget(self.plot_host)

    def render(self, result: AnalysisResult) -> None:
        if result.kind == "message":
            self.show_message(result.message or "当前没有可显示的结果。")
            return

        self.title_label.setText(result.title or "结果预览")
        subtitle = result.meta.get("subtitle") if isinstance(result.meta, dict) else None
        self.subtitle_label.setText(str(subtitle or result.title or result.node_id))

        figure = self.canvas.figure
        render_result_figure(figure, result)
        figure.canvas.draw_idle()
        self.stack.setCurrentWidget(self.plot_host)

    def show_message(self, message: str, title: str = "结果预览") -> None:
        self.title_label.setText(title)
        self.subtitle_label.setText("等待新的分析结果。")
        self.message_label.setText(message)
        self.stack.setCurrentWidget(self.message_label)
