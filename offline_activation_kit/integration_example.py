from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from offline_activation_kit.activation import ActivationConfig, LicenseManager, resolve_runtime_root
from offline_activation_kit.dialog import LicenseActivationDialog


CONFIG = ActivationConfig(
    app_name="示例程序",
    product_id="demo-desktop-app",
    storage_dir_name=".demo_desktop_app",
    key_prefix="DEMO-LIC-1.",
)


def ensure_license_access() -> bool:
    runtime_root = resolve_runtime_root()
    manager = LicenseManager(runtime_root, CONFIG)
    should_enforce = getattr(sys, "frozen", False) or manager.public_key_exists()
    if not should_enforce:
        return True

    status = manager.current_status()
    if status.valid:
        return True

    dialog = LicenseActivationDialog(manager, validation_result=status)
    if dialog.exec() and dialog.validation_result is not None:
        return dialog.validation_result.valid
    return False


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    if not ensure_license_access():
        return 1
    window = QMainWindow()
    window.setWindowTitle("示例程序")
    window.setCentralWidget(QLabel("授权通过，主程序已启动。"))
    window.resize(420, 180)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
