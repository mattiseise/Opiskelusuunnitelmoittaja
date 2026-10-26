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
