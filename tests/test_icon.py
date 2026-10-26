"""Sovelluskuvakkeet: valmiit tiedostot ja alustakohtainen valinta (scripts/make-icons.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from opiskelusuunnitelmoittaja.gui import app

PACKAGING = Path(__file__).resolve().parents[1] / "packaging"


def test_icon_files_have_all_sizes() -> None:
    assert Image.open(PACKAGING / "icon.png").size == (1024, 1024)
    ico = Image.open(PACKAGING / "icon.ico")
    assert {16, 20, 24, 32, 48, 256} <= {w for w, _h in ico.info["sizes"]}
    assert (PACKAGING / "icon.icns").stat().st_size > 0


def test_icon_path_prefers_ico_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "resource_path", lambda name: PACKAGING.parent / name)
    monkeypatch.setattr(app.sys, "platform", "win32")
    assert app.icon_path() == PACKAGING / "icon.ico"
    monkeypatch.setattr(app.sys, "platform", "darwin")
    assert app.icon_path() == PACKAGING / "icon.png"


def test_windows_app_id_only_for_windows_dev_version(monkeypatch: pytest.MonkeyPatch) -> None:
    # Paketoitu exe tunnistetaan omasta polustaan; tunnus irrottaisi kiinnitetyt pikakuvakkeet.
    # Oikea Windows-kutsu tarkistetaan CI:ssä (release.yml: Windows-käynnistin).
    monkeypatch.setattr(app.sys, "platform", "darwin")
    assert app.set_windows_app_id() is None
    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(app, "is_frozen", lambda: True)
    assert app.set_windows_app_id() is None


def test_launcher_script_reads_same_app_id() -> None:
    from opiskelusuunnitelmoittaja import APP_USER_MODEL_ID

    script = (PACKAGING.parent / "scripts" / "make-launcher.ps1").read_bytes()
    assert script.startswith(b"\xef\xbb\xbf")  # BOM: Windows PowerShell 5.1 lukee ääkköset
    init = (PACKAGING.parent / "src" / "opiskelusuunnitelmoittaja" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert f'APP_USER_MODEL_ID = "{APP_USER_MODEL_ID}"' in init  # skriptin Select-String-kuvio
    assert "^APP_USER_MODEL_ID = " in script.decode("utf-8-sig")
