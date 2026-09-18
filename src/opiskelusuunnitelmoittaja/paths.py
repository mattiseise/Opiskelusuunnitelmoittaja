"""Polut: paketoidun sovelluksen resurssit ja käyttäjäkohtainen data-hakemisto.

Kehityksessä resurssit (config.json, Opintosuunnitelmat.xlsx) ovat repon juuressa.
PyInstaller-paketissa ne ovat ``sys._MEIPASS``-hakemistossa, joka on vain luettava,
joten muokattavat kopiot viedään ensimmäisellä käynnistyksellä käyttäjän
data-hakemistoon (macOS: ~/Library/Application Support/OpintosuunnitelmanTayttaja,
Windows: %APPDATA%\\OpintosuunnitelmanTayttaja, Linux: ~/.local/share/opintosuunnitelmantayttaja).
Ympäristömuuttuja ``SUUNNITELMOITTAJA_HOME`` ohittaa data-hakemiston.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

from . import APP_SLUG

APP_NAME = APP_SLUG
USER_FILES = ("config.json", "Opintosuunnitelmat.xlsx")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Hakemisto, jossa paketoidut oletustiedostot ovat."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[2]


def resource_path(name: str) -> Path:
    return resource_root() / name


def user_data_dir() -> Path:
    override = os.environ.get("SUUNNITELMOITTAJA_HOME")
    if override:
        return Path(override).expanduser()
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if system == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / APP_NAME.lower()


def ensure_user_files() -> Path:
    """Luo data-hakemisto ja kopioi oletustiedostot sinne, jos ne puuttuvat."""
    target = user_data_dir()
    target.mkdir(parents=True, exist_ok=True)
    for name in USER_FILES:
        dst = target / name
        src = resource_path(name)
        if not dst.exists() and src.exists():
            shutil.copy2(src, dst)
    (target / "logs").mkdir(exist_ok=True)
    return target


def user_config_path() -> Path:
    return user_data_dir() / "config.json"
