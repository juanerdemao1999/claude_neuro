from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from nex5_analyzer.grouped_plv import GroupedPLVManifestEntry
from nex5_analyzer.config import SessionProfile
from nex5_analyzer.gui.grouped_plv_dialog import GroupedPLVWorkspaceDialog
from nex5_analyzer.gui.main_window import MainWindow


def test_grouped_plv_workspace_smoke(qapp, tmp_path: Path) -> None:
    dialog = GroupedPLVWorkspaceDialog(SessionProfile.default())
    button_texts = {button.text() for button in dialog.findChildren(QPushButton)}

    assert dialog.windowTitle() == "分组 PLV 工作台"
    assert "Import CSV" not in button_texts
    dialog.close()


def test_grouped_plv_workspace_builds_entries_from_gui_table(tmp_path: Path, qapp) -> None:
    first_file = tmp_path / "first.nex5"
    second_file = tmp_path / "second.nex5"
    first_file.write_text("", encoding="utf-8")
    second_file.write_text("", encoding="utf-8")
    dialog = GroupedPLVWorkspaceDialog(
        SessionProfile.default(),
        initial_entries=[
            GroupedPLVManifestEntry(file_path=first_file, group="control", subject="Mouse A", region="CA1"),
            GroupedPLVManifestEntry(file_path=second_file, group="treated", subject="Mouse B", region="CA1"),
        ],
    )

    dialog.file_table.item(1, 0).setCheckState(Qt.Unchecked)
    entries = dialog._entries_from_table()

    assert len(entries) == 1
    assert entries[0].file_path == first_file
    assert entries[0].group == "control"
    assert entries[0].subject == "Mouse A"
    assert entries[0].region == "CA1"
    dialog.close()


def test_main_window_exposes_grouped_plv_workspace_entry(tmp_path: Path, qapp) -> None:
    window = MainWindow(autosave_profile_path=tmp_path / "main_window_grouped_plv.json")

    assert window.open_grouped_plv_button.isEnabled() is True
    assert window.open_grouped_plv_button.text() == "打开分组 PLV"
    window.close()
