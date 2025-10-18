# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for bundling Active Recall PDF Studio on Windows 11."""

from pathlib import Path

project_root = Path(__file__).resolve().parent.parent

data_files = [
    (project_root / "README.md", "docs"),
    (project_root / "GUIDE.md", "docs"),
]

extra_datas = [(str(src), str(dest)) for src, dest in data_files]

block_cipher = None

a = Analysis(
    ['study_pdf/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=extra_datas,
    hiddenimports=[
        'PyQt6.QtSvg',
        'PyQt6.QtPdf',
        'PyQt6.QtPdfWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ActiveRecallPDF',
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ActiveRecallPDF',
)
