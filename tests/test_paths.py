"""Käyttäjän tiedostot: päivitys ei saa korvata käyttäjän omaa Exceliä eikä asetuksia."""

from __future__ import annotations

from pathlib import Path

import pytest

from opiskelusuunnitelmoittaja import paths


def test_update_never_overwrites_users_excel_or_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUUNNITELMOITTAJA_HOME", str(tmp_path / "data"))

    # Ensimmäinen käynnistys: paketin pohjat kopioidaan käyttäjän data-hakemistoon
    target = paths.ensure_user_files()
    excel = target / "Opintosuunnitelmat.xlsx"
    config = target / "config.json"
    assert excel.read_bytes() == paths.resource_path("Opintosuunnitelmat.xlsx").read_bytes()
    assert config.exists()

    # Käyttäjä muokkaa omaa Exceliään ja asetuksiaan
    excel.write_bytes(b"opettajan oma excel")
    config.write_text('{"oma": true}', encoding="utf-8")

    # Päivitys: uusi paketti tuo erilaiset pohjat
    new_package = tmp_path / "uusi-paketti"
    new_package.mkdir()
    (new_package / "Opintosuunnitelmat.xlsx").write_bytes(b"uusi pohja")
    (new_package / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "resource_root", lambda: new_package)
    paths.ensure_user_files()

    assert excel.read_bytes() == b"opettajan oma excel"
    assert config.read_text(encoding="utf-8") == '{"oma": true}'


def test_missing_user_excel_is_restored_from_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUUNNITELMOITTAJA_HOME", str(tmp_path / "data"))
    target = paths.ensure_user_files()
    (target / "Opintosuunnitelmat.xlsx").unlink()  # käyttäjä poisti: saa uuden pohjan
    paths.ensure_user_files()
    assert (target / "Opintosuunnitelmat.xlsx").exists()
