from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtWidgets import QApplication

from .gui.license_dialog import LicenseActivationDialog
from .gui.main_window import MainWindow
from .gui.theme import ensure_app_theme
from .licensing import LicenseManager


def _resolve_runtime_root(explicit_root: Path | None = None) -> Path:
    if explicit_root is not None:
        return explicit_root.resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def _ensure_license_access(runtime_root: Path) -> bool:
    manager = LicenseManager(runtime_root)
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


def main(*, preferred_files: Sequence[Path] | None = None, runtime_root: Path | None = None) -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    ensure_app_theme()
    resolved_runtime_root = _resolve_runtime_root(runtime_root)
    if not _ensure_license_access(resolved_runtime_root):
        return 1
    window = MainWindow()
    for sample_path in preferred_files or ():
        if Path(sample_path).exists():
            window.load_session(Path(sample_path))
            break
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
