# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-määrittely: Opiskelusuunnitelmoittaja GUI + Playwright-ajuri.

Ajo repon juuresta:  uv run pyinstaller packaging/Opiskelusuunnitelmoittaja.spec --noconfirm
Tulos: dist/Opiskelusuunnitelmoittaja/ (Linux/Windows) tai dist/Opiskelusuunnitelmoittaja.app (macOS).
"""

import sys
from pathlib import Path

import playwright

ROOT = Path(SPECPATH).parent
DRIVER_DIR = Path(playwright.__file__).parent / "driver"
# PyInstaller muuntaa PNG:n .icns/.ico-muotoon Pillow'lla; Windowsissa käytetään valmista .ico:ta.
ICON = str(ROOT / "packaging" / ("icon.ico" if sys.platform == "win32" else "icon.png"))

# Playwrightin Node-ajuri ja JS-paketti mukaan samaan suhteelliseen paikkaan, josta
# playwright.__file__ sen odottaa löytävän (<_MEIPASS>/playwright/driver).
driver_tree = Tree(
    str(DRIVER_DIR),
    prefix="playwright/driver",
    excludes=["*.d.ts", "types", "README.md", "*.mjs"],
)

datas = [
    (str(ROOT / "config.json"), "."),
    (str(ROOT / "Opintosuunnitelmat.xlsx"), "."),
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["opiskelusuunnitelmoittaja.cli"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtPdf",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Opiskelusuunnitelmoittaja",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    driver_tree,
    strip=False,
    upx=False,
    name="Opiskelusuunnitelmoittaja",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Opiskelusuunnitelmoittaja.app",
        icon=ICON,
        bundle_identifier="fi.seise.opiskelusuunnitelmoittaja",
        info_plist={
            "CFBundleShortVersionString": "2.1.0",
            "CFBundleVersion": "2.1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSHumanReadableCopyright": "Matti Seise",
        },
    )
