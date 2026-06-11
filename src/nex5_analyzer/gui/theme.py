from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget


APP_STYLESHEET = """
QWidget {
    background: #f4f7fb;
    color: #1f2937;
    font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background: #eef3f8;
}

QWidget#surface {
    background: #ffffff;
    border: 1px solid #dbe4ee;
    border-radius: 16px;
}

QLabel[role="hero-title"] {
    font-size: 24px;
    font-weight: 700;
    color: #16324f;
    background: transparent;
}

QLabel[role="section-title"] {
    font-size: 15px;
    font-weight: 700;
    color: #16324f;
    background: transparent;
}

QLabel[role="caption"] {
    color: #637289;
    background: transparent;
}

QLabel[role="muted"] {
    color: #70839a;
    background: transparent;
}

QLabel[role="status"] {
    border-radius: 999px;
    padding: 7px 12px;
    font-weight: 600;
}

QLabel[tone="info"] {
    background: #eaf2ff;
    border: 1px solid #c8dbff;
    color: #24538a;
}

QLabel[tone="ok"] {
    background: #eaf8ef;
    border: 1px solid #cbe8d3;
    color: #23613e;
}

QLabel[tone="warn"] {
    background: #fff5e8;
    border: 1px solid #f2dcc0;
    color: #8c5a1d;
}

QLabel[tone="error"] {
    background: #fdeeee;
    border: 1px solid #f0c8c8;
    color: #9d2f2f;
}

QPushButton {
    background: #2f6fb6;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 9px 16px;
    font-weight: 600;
    min-height: 18px;
}

QPushButton:hover {
    background: #245f9e;
}

QPushButton:pressed {
    background: #1e4f83;
}

QPushButton:disabled {
    background: #c7d4e4;
    color: #7a899c;
}

QPushButton[variant="secondary"] {
    background: #ffffff;
    color: #234564;
    border: 1px solid #cbd8e6;
}

QPushButton[variant="secondary"]:hover {
    background: #f6faff;
}

QLineEdit,
QTextEdit,
QTreeWidget,
QTableWidget,
QScrollArea,
QAbstractSpinBox {
    background: #ffffff;
    border: 1px solid #d6e0ea;
    border-radius: 10px;
}

QLineEdit,
QAbstractSpinBox {
    padding: 6px 10px;
    min-height: 18px;
}

QTextEdit,
QTreeWidget,
QTableWidget {
    padding: 4px;
}

QLineEdit:focus,
QTextEdit:focus,
QTreeWidget:focus,
QTableWidget:focus,
QAbstractSpinBox:focus {
    border: 1px solid #7ea8d8;
}

QGroupBox {
    background: #ffffff;
    border: 1px solid #dbe4ee;
    border-radius: 16px;
    margin-top: 14px;
    padding: 16px 14px 14px 14px;
    font-weight: 700;
    color: #16324f;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

QHeaderView::section {
    background: #edf3fa;
    color: #234564;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid #dbe4ee;
    padding: 8px;
}

QTableWidget {
    gridline-color: #edf2f7;
}

QTableWidget::item:selected,
QTreeWidget::item:selected {
    background: #dcecff;
    color: #16324f;
}

QProgressBar {
    background: #e8eef5;
    border: none;
    border-radius: 999px;
    min-height: 12px;
    text-align: center;
    color: #234564;
}

QProgressBar::chunk {
    background: #2f6fb6;
    border-radius: 999px;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px;
}

QScrollBar::handle:vertical {
    background: #cbd8e6;
    border-radius: 999px;
    min-height: 20px;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 4px;
}

QScrollBar::handle:horizontal {
    background: #cbd8e6;
    border-radius: 999px;
    min-width: 20px;
}

QScrollBar::add-line,
QScrollBar::sub-line {
    width: 0;
    height: 0;
}
"""


def ensure_app_theme() -> None:
    app = QApplication.instance()
    if app is None:
        return
    if getattr(app, "_nex5_theme_applied", False):
        return

    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    app.setStyleSheet(APP_STYLESHEET)
    app._nex5_theme_applied = True


def set_status_tone(widget: QWidget, tone: str) -> None:
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
