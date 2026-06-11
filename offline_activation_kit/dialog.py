from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .activation import LicenseManager, LicenseValidationResult


class LicenseActivationDialog(QDialog):
    def __init__(
        self,
        manager: LicenseManager,
        *,
        validation_result: LicenseValidationResult | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.validation_result = validation_result

        self.setWindowTitle(f"{self.manager.config.app_name} 授权激活")
        self.resize(720, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        header_layout.setSpacing(6)
        layout.addWidget(header)

        title = QLabel("当前电脑尚未激活")
        title.setProperty("role", "hero-title")
        header_layout.addWidget(title)

        subtitle = QLabel("请把本机机器码发给软件提供方，拿到激活密钥后粘贴到下方，或直接导入密钥文件。")
        subtitle.setWordWrap(True)
        subtitle.setProperty("role", "caption")
        header_layout.addWidget(subtitle)

        self.status_label = QLabel(self._status_text())
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        machine_row = QHBoxLayout()
        machine_row.setSpacing(8)
        layout.addLayout(machine_row)

        machine_row.addWidget(QLabel("本机机器码："))
        self.machine_code_edit = QLineEdit(self.manager.machine_identity.fingerprint)
        self.machine_code_edit.setReadOnly(True)
        machine_row.addWidget(self.machine_code_edit, 1)

        copy_machine_button = QPushButton("复制机器码")
        copy_machine_button.clicked.connect(self._copy_machine_code)
        machine_row.addWidget(copy_machine_button)

        save_machine_button = QPushButton("保存机器码")
        save_machine_button.clicked.connect(self._save_machine_code)
        machine_row.addWidget(save_machine_button)

        layout.addWidget(QLabel("激活密钥："))
        self.key_edit = QTextEdit()
        self.key_edit.setPlaceholderText("请粘贴激活密钥，或点击“导入密钥文件”。")
        layout.addWidget(self.key_edit, 1)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        layout.addLayout(action_row)

        import_button = QPushButton("导入密钥文件")
        import_button.clicked.connect(self._import_license)
        action_row.addWidget(import_button)

        activate_button = QPushButton("立即激活")
        activate_button.clicked.connect(self._activate_from_key_text)
        action_row.addWidget(activate_button)

        action_row.addStretch(1)

        exit_button = QPushButton("退出程序")
        exit_button.clicked.connect(self.reject)
        action_row.addWidget(exit_button)

    def _status_text(self) -> str:
        if self.validation_result is None:
            return "未检测到有效授权。"
        return self.validation_result.message

    def _copy_machine_code(self) -> None:
        QApplication.clipboard().setText(self.manager.machine_identity.fingerprint)
        QMessageBox.information(self, "机器码", "机器码已复制到剪贴板。")

    def _save_machine_code(self) -> None:
        default_path = Path.cwd() / "machine_code.txt"
        path, _ = QFileDialog.getSaveFileName(self, "保存机器码", str(default_path), "Text Files (*.txt)")
        if not path:
            return
        Path(path).write_text(self.manager.machine_identity.fingerprint, encoding="utf-8")
        QMessageBox.information(self, "机器码", f"机器码已保存到：{path}")

    def _activate_from_key_text(self) -> None:
        activation_key = self.key_edit.toPlainText().strip()
        if not activation_key:
            QMessageBox.warning(self, "激活失败", "请先输入激活密钥。")
            return
        self._handle_activation_result(self.manager.install_activation_key(activation_key))

    def _import_license(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入密钥文件",
            str(Path.cwd()),
            "License Key Files (*.key *.json *.txt);;All Files (*.*)",
        )
        if not path:
            return
        self._handle_activation_result(self.manager.install_license(Path(path)))

    def _handle_activation_result(self, result: LicenseValidationResult) -> None:
        self.validation_result = result
        self.status_label.setText(self._status_text())
        if result.valid:
            customer_name = result.claims.get("customer_name", "未知客户") if result.claims else "未知客户"
            QMessageBox.information(self, "激活成功", f"{self.manager.config.app_name} 已激活。\n客户：{customer_name}")
            self.accept()
            return
        QMessageBox.warning(self, "激活失败", result.message)
