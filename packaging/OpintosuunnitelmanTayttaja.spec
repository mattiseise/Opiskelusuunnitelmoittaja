# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-määrittely: Opintosuunnitelman muokkaaja (GUI) + Playwright-ajuri.

Ajo repon juuresta:  uv run pyinstaller packaging/OpintosuunnitelmanTayttaja.spec --noconfirm
Tulos: dist/OpintosuunnitelmanTayttaja/ (Linux/Windows) tai dist/Opintosuunnitelman muokkaaja.app (macOS).
"""

import sys
from pathlib import Path

import playwright

ROOT = Path(SPECPATH).parent
DRIVER_DIR = Path(playwright.__file__).parent / "driver"
sys.path.insert(0, str(ROOT / "src"))
from opiskelusuunnitelmoittaja import APP_SLUG, APP_TITLE, __version__  # noqa: E402
# Valmiit monikokoiset kuvakkeet (scripts/make-icons.py): pienet koot on piirretty erikseen
# teräviksi, joten PyInstallerin ei tarvitse pienentää 1024 px:n PNG:tä.
_ICON_FILE = {"win32": "icon.ico", "darwin": "icon.icns"}.get(sys.platform, "icon.png")
ICON = str(ROOT / "packaging" / _ICON_FILE)

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
    (str(ROOT / "packaging" / "icon.png"), "."),
    (str(ROOT / "packaging" / "icon.ico"), "."),  # Windowsin ikkunakuvake (gui/app.py)
    # Public Sans + Source Serif 4 (OFL) samaan paikkaan, josta gui/theme.py ne lataa
    (str(ROOT / "src" / "opiskelusuunnitelmoittaja" / "gui" / "fonts"), "opiskelusuunnitelmoittaja/gui/fonts"),
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



def windows_version_info():
    """Exe:n versiotiedot. Windows näyttää FileDescriptionin sovelluksen nimenä
    (kiinnitetty kuvake, Tehtävienhallinta, Avaa sovelluksessa); ilman niitä nimi olisi
    tiedostonimi OpintosuunnitelmanTayttaja."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    numbers = (*(int(n) for n in __version__.split(".")), 0)
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040b04b0",  # suomi, Unicode
                        [
                            StringStruct("CompanyName", "Matti Seise"),
                            StringStruct("FileDescription", APP_TITLE),
                            StringStruct("FileVersion", __version__),
                            StringStruct("InternalName", APP_SLUG),
                            StringStruct("OriginalFilename", f"{APP_SLUG}.exe"),
                            StringStruct("ProductName", APP_TITLE),
                            StringStruct("ProductVersion", __version__),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [0x040B, 1200])]),
        ],
    )


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OpintosuunnitelmanTayttaja",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=ICON,
    version=windows_version_info() if sys.platform == "win32" else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    driver_tree,
    strip=False,
    upx=False,
    name="OpintosuunnitelmanTayttaja",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Opintosuunnitelman muokkaaja.app",
        icon=ICON,
        bundle_identifier="fi.seise.opintosuunnitelmantayttaja",
        info_plist={
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSHumanReadableCopyright": "Matti Seise",
            "CFBundleDisplayName": "Opintosuunnitelman muokkaaja",
            "CFBundleName": "Opintosuunnitelman muokkaaja",
        },
    )
