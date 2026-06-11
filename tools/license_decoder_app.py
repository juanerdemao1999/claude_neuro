from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nex5_analyzer.licensing import (
    format_license_artifact_inspection,
    inspect_license_artifact_text,
    load_license_document_text,
)


class LicenseDecoderWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NEX5 授权解码查看器")
        self.resize(1100, 760)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        intro = QLabel(
            "把激活码或授权 JSON 粘贴到左侧，或直接打开 .key / .json 文件。"
            " 该工具只做解析与查看，不会写入授权。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        action_row = QHBoxLayout()
        layout.addLayout(action_row)

        open_button = QPushButton("打开文件")
        open_button.clicked.connect(self._open_file)
        action_row.addWidget(open_button)

        inspect_button = QPushButton("开始解析")
        inspect_button.clicked.connect(self._inspect_current_text)
        action_row.addWidget(inspect_button)

        clear_button = QPushButton("清空")
        clear_button.clicked.connect(self._clear_all)
        action_row.addWidget(clear_button)

        copy_button = QPushButton("复制结果")
        copy_button.clicked.connect(self._copy_report)
        action_row.addWidget(copy_button)

        action_row.addStretch(1)

        self.status_label = QLabel("等待输入。")
        layout.addWidget(self.status_label)

        splitter = QSplitter()
        layout.addWidget(splitter, 1)

        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("在这里粘贴激活码，或粘贴完整授权 JSON。")
        splitter.addWidget(self.input_edit)

        tabs = QTabWidget()
        splitter.addWidget(tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        self.report_edit = QPlainTextEdit()
        self.report_edit.setReadOnly(True)
        tabs.addTab(self.report_edit, "解析结果")

        self.document_edit = QPlainTextEdit()
        self.document_edit.setReadOnly(True)
        tabs.addTab(self.document_edit, "原始文档")

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开授权文件",
            str(PROJECT_ROOT),
            "License Files (*.key *.json *.txt);;All Files (*.*)",
        )
        if not path:
            return
        selected_path = Path(path)
        self.input_edit.setPlainText(selected_path.read_text(encoding="utf-8"))
        self.status_label.setText(f"已载入: {selected_path}")
        self._inspect_current_text()

    def _inspect_current_text(self) -> None:
        raw_text = self.input_edit.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "无法解析", "请先输入激活码或授权 JSON。")
            return
        try:
            inspection = inspect_license_artifact_text(raw_text)
            document = load_license_document_text(raw_text)
        except Exception as exc:  # pragma: no cover - GUI error path
            self.status_label.setText("解析失败。")
            QMessageBox.warning(self, "解析失败", str(exc))
            return

        self.report_edit.setPlainText(format_license_artifact_inspection(inspection))
        self.document_edit.setPlainText(json.dumps(document, indent=2, ensure_ascii=False))
        self.status_label.setText("解析完成。")

    def _clear_all(self) -> None:
        self.input_edit.clear()
        self.report_edit.clear()
        self.document_edit.clear()
        self.status_label.setText("已清空。")

    def _copy_report(self) -> None:
        report = self.report_edit.toPlainText().strip()
        if not report:
            QMessageBox.warning(self, "无法复制", "请先完成解析。")
            return
        QApplication.clipboard().setText(report)
        self.status_label.setText("解析结果已复制。")


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    window = LicenseDecoderWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
