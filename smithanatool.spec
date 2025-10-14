# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files


BASE = Path(os.path.abspath("."))
ICON_PATH = BASE / "smithanatool_qt" / "assets" / "smithanatool.ico"

ENTRY = "main.py"
APPNAME = "SmithanaTool"
datas = [(r"smithanatool_qt/assets", "assets")]
hiddenimports = [
    "smithanatool_qt.tabs.transform.tab",
    "smithanatool_qt.tabs.parser_manhwa_tab",
    "smithanatool_qt.tabs.parser_novel_tab",
    "smithanatool_qt.tabs.info_tab",
]

# ----------------- Qt essentials (без WebEngine) -----------------
QT_PLUGINS = [
    ("PySide6/Qt/plugins/platforms", "PySide6/Qt/plugins/platforms"),
    ("PySide6/Qt/plugins/styles", "PySide6/Qt/plugins/styles"),
    ("PySide6/Qt/plugins/imageformats", "PySide6/Qt/plugins/imageformats"),
    ("PySide6/Qt/plugins/iconengines", "PySide6/Qt/plugins/iconengines"),
]
QT_RES_DIRS = [
    ("PySide6/Qt/resources", "PySide6/Qt/resources"),
    ("PySide6/Qt/translations", "PySide6/Qt/translations"),  # можно удалить из dist для экономии
]


# ----------------- Явные исключения (WebEngine и прочее лишнее) -----------------
excludes = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngine",
    "PySide6.QtNetworkAuth",
    "PySide6.QtHelp",
    "PySide6.QtTest",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtWebSockets",
    "PySide6.QtBluetooth",
]

block_cipher = None

a = Analysis(
    [ENTRY],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    name=APPNAME,
    exclude_binaries=True,
    icon=str(ICON_PATH),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=APPNAME,
)
