from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from offline_activation_kit.activation import (
        ActivationConfig,
        build_license_claims,
        encode_activation_key,
        sign_license_claims,
    )
else:
    from .activation import ActivationConfig, build_license_claims, encode_activation_key, sign_license_claims

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


CONFIG = ActivationConfig(
    app_name="你的软件名",
    product_id="your-product-id",
    storage_dir_name=".your_app",
    key_prefix="YOURAPP-LIC-1.",
)

PRIVATE_KEY_FILE_NAME = "license_private_key.pem"
MACHINE_CODE_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")
TOOL_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class SigningKeyPaths:
    private_key_path: Path
    public_key_path: Path
    publish_public_key_path: Path
    publish_public_key_matches: bool
    created_new_keypair: bool


def _public_key_pem_from_private_key(private_key_pem: bytes) -> bytes:
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def ensure_signing_keypair(tool_root: Path = TOOL_ROOT) -> SigningKeyPaths:
    secrets_dir = tool_root / ".secrets"
    publish_dir = tool_root / "publish"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    publish_dir.mkdir(parents=True, exist_ok=True)

    private_key_path = secrets_dir / PRIVATE_KEY_FILE_NAME
    public_key_path = secrets_dir / CONFIG.public_key_file_name
    publish_public_key_path = publish_dir / CONFIG.public_key_file_name

    created_new_keypair = False
    if not private_key_path.exists():
        private_key = Ed25519PrivateKey.generate()
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_key_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_key_path.write_bytes(private_key_pem)
        public_key_path.write_bytes(public_key_pem)
        created_new_keypair = True
    else:
        private_key_pem = private_key_path.read_bytes()
        public_key_pem = _public_key_pem_from_private_key(private_key_pem)
        if not public_key_path.exists() or public_key_path.read_bytes() != public_key_pem:
            public_key_path.write_bytes(public_key_pem)

    if not publish_public_key_path.exists() or publish_public_key_path.read_bytes() != public_key_pem:
        publish_public_key_path.write_bytes(public_key_pem)

    return SigningKeyPaths(
        private_key_path=private_key_path,
        public_key_path=public_key_path,
        publish_public_key_path=publish_public_key_path,
        publish_public_key_matches=publish_public_key_path.read_bytes() == public_key_pem,
        created_new_keypair=created_new_keypair,
    )


def _default_license_id() -> str:
    return "LIC-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def _parse_optional_expiry(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def make_activation_key(
    *,
    private_key_path: Path,
    machine_code: str,
    customer_name: str,
    license_id: str,
    expires_at: str = "",
    config: ActivationConfig = CONFIG,
) -> str:
    machine_code = machine_code.strip().lower()
    if not MACHINE_CODE_PATTERN.fullmatch(machine_code):
        raise ValueError("机器码必须是 64 位十六进制字符串，请确认复制完整。")
    customer_name = customer_name.strip()
    if not customer_name:
        raise ValueError("客户名称不能为空。")
    license_id = license_id.strip()
    if not license_id:
        raise ValueError("许可证编号不能为空。")
    claims = build_license_claims(
        config=config,
        customer_name=customer_name,
        machine_fingerprint=machine_code,
        license_id=license_id,
        expires_at=_parse_optional_expiry(expires_at),
        features=["desktop"],
    )
    signed_license = sign_license_claims(claims, private_key_path.read_bytes())
    return encode_activation_key(signed_license, config)


class LicenseGeneratorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.key_paths = ensure_signing_keypair()

        self.setWindowTitle(f"{CONFIG.app_name} 授权密钥生成器")
        self.resize(780, 560)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("授权密钥生成器")
        title.setProperty("role", "hero-title")
        layout.addWidget(title)

        self.status_label = QLabel(self._key_status_text())
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        form = QFormLayout()
        form.setSpacing(10)
        layout.addLayout(form)

        self.machine_code_edit = QLineEdit()
        self.machine_code_edit.setPlaceholderText("粘贴客户发来的 64 位机器码")
        form.addRow("客户机器码", self.machine_code_edit)

        self.customer_edit = QLineEdit("客户名称")
        form.addRow("客户名称", self.customer_edit)

        self.license_id_edit = QLineEdit(_default_license_id())
        form.addRow("许可证编号", self.license_id_edit)

        self.expiry_edit = QLineEdit()
        self.expiry_edit.setPlaceholderText("可留空；示例：2027-04-13T00:00:00+00:00")
        form.addRow("到期时间", self.expiry_edit)

        output_row = QHBoxLayout()
        self.output_path_edit = QLineEdit(str((TOOL_ROOT / "licenses" / CONFIG.activation_key_file_name).resolve()))
        output_row.addWidget(self.output_path_edit, 1)
        browse_button = QPushButton("选择")
        browse_button.clicked.connect(self._choose_output_path)
        output_row.addWidget(browse_button)
        form.addRow("输出文件", output_row)

        button_row = QHBoxLayout()
        layout.addLayout(button_row)

        generate_button = QPushButton("生成密钥文件")
        generate_button.clicked.connect(self._generate_key)
        button_row.addWidget(generate_button)

        copy_button = QPushButton("复制生成结果")
        copy_button.clicked.connect(self._copy_generated_key)
        button_row.addWidget(copy_button)

        button_row.addStretch(1)

        self.generated_key_view = QTextEdit()
        self.generated_key_view.setReadOnly(True)
        self.generated_key_view.setPlaceholderText("生成后的激活密钥会显示在这里，同时会写入输出文件。")
        layout.addWidget(self.generated_key_view, 1)

    def _key_status_text(self) -> str:
        lines = [
            f"私钥位置：{self.key_paths.private_key_path}",
            f"可发布公钥：{self.key_paths.publish_public_key_path}",
        ]
        if self.key_paths.created_new_keypair:
            lines.append("首次运行已自动生成密钥对。把 publish 目录里的公钥放进客户程序并重新打包。")
        if not self.key_paths.publish_public_key_matches:
            lines.append("注意：publish 目录的公钥与当前私钥不匹配，请重新同步公钥。")
        return "\n".join(lines)

    def _choose_output_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存密钥文件",
            self.output_path_edit.text().strip(),
            "License Key Files (*.key);;Text Files (*.txt);;All Files (*.*)",
        )
        if path:
            self.output_path_edit.setText(path)

    def _generate_key(self) -> None:
        try:
            activation_key = make_activation_key(
                private_key_path=self.key_paths.private_key_path,
                machine_code=self.machine_code_edit.text(),
                customer_name=self.customer_edit.text(),
                license_id=self.license_id_edit.text(),
                expires_at=self.expiry_edit.text(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "生成失败", str(exc))
            return

        output_path = Path(self.output_path_edit.text().strip()).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(activation_key, encoding="utf-8")
        self.generated_key_view.setPlainText(activation_key)
        QMessageBox.information(self, "生成成功", f"密钥文件已生成：\n{output_path}")

    def _copy_generated_key(self) -> None:
        activation_key = self.generated_key_view.toPlainText().strip()
        if not activation_key:
            QMessageBox.warning(self, "复制失败", "请先生成密钥。")
            return
        QApplication.clipboard().setText(activation_key)
        QMessageBox.information(self, "复制成功", "密钥已复制到剪贴板。")


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    window = LicenseGeneratorWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
