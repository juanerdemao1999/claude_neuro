# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files

project_root = Path.cwd()
sys.path.insert(0, str(project_root / "src"))

from nex5_analyzer.build_support import collect_optional_runtime_files, collect_required_pyinstaller_data_files

datas = collect_required_pyinstaller_data_files(collect_data_files)
datas.extend(collect_optional_runtime_files(project_root))


a = Analysis(
    ["launch_gui.py"],
    pathex=[str(project_root), str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "scienceplots",
        "matplotlib.backends.backend_qtagg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt5.sip",
        "PyQt6",
        "PySide2",
        "pytest",
        "_pytest",
        "IPython",
        "jedi",
        "tkinter",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NEX5SpikeLFPAnalyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NEX5SpikeLFPAnalyzer",
)
