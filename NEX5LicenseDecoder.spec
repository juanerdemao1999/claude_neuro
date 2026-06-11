# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

project_root = Path.cwd()
sys.path.insert(0, str(project_root / "src"))


a = Analysis(
    ["tools/license_decoder_app.py"],
    pathex=[str(project_root), str(project_root / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name="NEX5LicenseDecoder",
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
    onefile=True,
)
