from pathlib import Path

from nex5_analyzer.build_support import (
    collect_optional_runtime_files,
    collect_required_pyinstaller_data_files,
    required_pyinstaller_data_packages,
)
from nex5_analyzer.licensing import PUBLIC_KEY_FILE_NAME


def test_required_pyinstaller_data_packages_include_runtime_data_dependencies() -> None:
    assert "scienceplots" in required_pyinstaller_data_packages()
    assert "elephant" in required_pyinstaller_data_packages()


def test_required_pyinstaller_data_packages_do_not_repeat_entries() -> None:
    packages = required_pyinstaller_data_packages()

    assert len(packages) == len(set(packages))


def test_collect_required_pyinstaller_data_files_collects_each_required_package() -> None:
    seen: list[str] = []

    def fake_collect_data_files(package_name: str) -> list[tuple[str, str]]:
        seen.append(package_name)
        return [(f"{package_name}/payload", package_name)]

    datas = collect_required_pyinstaller_data_files(fake_collect_data_files)

    assert seen == list(required_pyinstaller_data_packages())
    assert datas == [
        ("scienceplots/payload", "scienceplots"),
        ("elephant/payload", "elephant"),
    ]


def test_collect_optional_runtime_files_includes_public_key_when_present(tmp_path: Path) -> None:
    public_key_path = tmp_path / PUBLIC_KEY_FILE_NAME
    public_key_path.write_text("public-key", encoding="utf-8")

    datas = collect_optional_runtime_files(tmp_path)

    assert datas == [(str(public_key_path), ".")]
