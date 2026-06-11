from __future__ import annotations

from pathlib import Path
from typing import Callable

from .licensing import PUBLIC_KEY_FILE_NAME


def required_pyinstaller_data_packages() -> tuple[str, ...]:
    """Packages whose runtime data files must ship with the frozen app."""
    return (
        "scienceplots",
        "elephant",
    )


def collect_required_pyinstaller_data_files(
    collect_data_files: Callable[[str], list[tuple[str, str]]],
) -> list[tuple[str, str]]:
    datas: list[tuple[str, str]] = []
    for package_name in required_pyinstaller_data_packages():
        datas.extend(collect_data_files(package_name))
    return datas


def collect_optional_runtime_files(project_root: Path) -> list[tuple[str, str]]:
    datas: list[tuple[str, str]] = []
    public_key_path = Path(project_root) / PUBLIC_KEY_FILE_NAME
    if public_key_path.exists():
        datas.append((str(public_key_path), "."))
    return datas
