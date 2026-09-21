from __future__ import annotations

import json
from pathlib import Path

import pytest

from opiskelusuunnitelmoittaja.config import (
    BrowserConfig,
    Config,
    ConfigError,
    config_from_dict,
    load_config,
)


def test_defaults_when_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg == Config()
    assert cfg.field_names == ["osaamistavoite", "laajuus", "suoritustapa", "suoritusajankohta"]


def test_explicit_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="ei löydy"):
        load_config(tmp_path / "ei.json")


def test_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{ ei json", encoding="utf-8")
    with pytest.raises(ConfigError, match="Virheellinen JSON"):
        load_config(path)


def test_partial_config_is_merged_with_defaults() -> None:
    cfg = config_from_dict(
        {
            "browser": {"remote_debugging_port": 9333, "page_url_contains": "wilma"},
            "selectors": {"add_row_button": "#lisaa"},
            "separator_row_between_sheets": False,
        }
    )
    assert cfg.browser.remote_debugging_port == 9333
    assert cfg.browser.page_url_contains == "wilma"
    assert cfg.browser.timeout_ms == 10_000
    assert cfg.selectors.add_row_button == "#lisaa"
    assert cfg.selectors.table_body == "form table tbody"
    assert cfg.separator_row_between_sheets is False
    assert cfg.excel_columns["laajuus"] == "Laajuus"


def test_repo_config_json_loads() -> None:
    repo_cfg = Path(__file__).resolve().parents[1] / "config.json"
    cfg = config_from_dict(json.loads(repo_cfg.read_text(encoding="utf-8")))
    assert cfg.excel_file.name == "Opintosuunnitelmat.xlsx"
    assert set(cfg.selectors.field_cells) == set(cfg.excel_columns)


def test_user_data_dir_default_is_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cfg = BrowserConfig()
    assert cfg.resolved_user_data_dir() == tmp_path / ".opiskelusuunnitelmoittaja/chrome-profile"
    assert "--remote-debugging-port=9222" in cfg.launch_args()


def test_launch_command_mentions_port_and_profile() -> None:
    cfg = BrowserConfig(user_data_dir="/tmp/profiili", chrome_path="/x/chrome")
    cmd = cfg.launch_command()
    assert "--remote-debugging-port=9222" in cmd
    assert str(Path("/tmp/profiili")) in cmd  # Windowsissa polku tulostuu kenoviivoilla


def test_fill_section_parsed_and_roundtripped() -> None:
    from opiskelusuunnitelmoittaja.config import config_to_dict
    from opiskelusuunnitelmoittaja.fillmode import FillMode

    assert Config().fill_mode is FillMode.APPEND
    assert Config().resolved_key_field == "osaamistavoite"
    cfg = config_from_dict(
        {
            "fill": {"mode": "korvaa", "key_field": "laajuus"},
            "selectors": {"remove_row_button": "[id$='__del']"},
        }
    )
    assert cfg.fill_mode is FillMode.REPLACE
    assert cfg.key_field == "laajuus"
    assert cfg.selectors.remove_row_button == "[id$='__del']"
    # tuntematon arvo → oletus, ei kaatumista
    assert config_from_dict({"fill": {"mode": "höpö"}}).fill_mode is FillMode.APPEND
    # tuntematon avainkenttä → ensimmäinen kenttä
    assert config_from_dict({"fill": {"key_field": "olematon"}}).resolved_key_field == (
        "osaamistavoite"
    )
    data = config_to_dict(cfg)
    assert data["fill"] == {"mode": "replace", "key_field": "laajuus"}
    assert data["selectors"]["remove_row_button"] == "[id$='__del']"
    assert config_from_dict(data).fill_mode is FillMode.REPLACE
