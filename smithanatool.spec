# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


BASE = Path(os.path.abspath("."))
ICON_PATH = BASE / "smithanatool_qt" / "assets" / "smithanatool.ico"

ENTRY = "main.py"
APPNAME = "SmithanaTool"
datas = [
    (r"smithanatool_qt/assets", "assets"),
    (r"smithanatool_qt/styles", "smithanatool_qt/styles"),
]

hiddenimports = [
    "smithanatool_qt.tabs.workshop.tab",
    "smithanatool_qt.tabs.parsers.tab",
    "smithanatool_qt.tabs.info_tab",
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
