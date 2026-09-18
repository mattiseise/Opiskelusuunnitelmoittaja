"""Asetusten lataus ja oletusarvot.

Asetukset luetaan ``config.json``-tiedostosta. Puuttuvat avaimet täydennetään
oletuksilla, joten tiedostoon tarvitsee kirjoittaa vain se, mikä poikkeaa.
"""

from __future__ import annotations

import json
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contact import TeacherContact
from .wizard import WizardConfig

DEFAULT_CONFIG_PATH = Path("config.json")
DEFAULT_PROFILE_DIRNAME = ".opiskelusuunnitelmoittaja/chrome-profile"


class ConfigError(Exception):
    """Asetustiedosto puuttuu tai on virheellinen."""


@dataclass(frozen=True, slots=True)
class BrowserConfig:
    remote_debugging_port: int = 9222
    user_data_dir: str = ""  # tyhjä = oletus kotihakemistossa
    chrome_path: str = ""  # tyhjä = tunnistetaan automaattisesti
    page_url_contains: str = ""  # tyhjä = ensimmäinen välilehti, jolla lomake näkyy
    timeout_ms: int = 10_000

    def resolved_user_data_dir(self) -> Path:
        if self.user_data_dir:
            return Path(self.user_data_dir).expanduser()
        return Path.home() / DEFAULT_PROFILE_DIRNAME

    def resolved_chrome_path(self) -> str | None:
        if self.chrome_path:
            return self.chrome_path
        return find_chrome()

    def launch_args(self) -> list[str]:
        return [
            f"--remote-debugging-port={self.remote_debugging_port}",
            f"--user-data-dir={self.resolved_user_data_dir()}",
        ]

    def launch_command(self) -> str:
        """Ihmisluettava käynnistyskomento nykyiselle käyttöjärjestelmälle."""
        chrome = self.resolved_chrome_path() or "<chrome>"
        args = " ".join(_quote(a) for a in self.launch_args())
        if platform.system() == "Darwin":
            return f'open -na "Google Chrome" --args {args}'
        return f"{_quote(chrome)} {args}"


@dataclass(frozen=True, slots=True)
class Selectors:
    """Lomakkeen lokaattorit. CSS tai XPath (``xpath=...``) – Playwright tunnistaa molemmat."""

    table_body: str = "form table tbody"
    add_row_button: str = "[id$='__add']"
    field_cells: dict[str, str] = field(
        default_factory=lambda: {
            "osaamistavoite": "td:nth-child(1)",
            "laajuus": "td:nth-child(2)",
            "suoritustapa": "td:nth-child(3)",
            "suoritusajankohta": "td:nth-child(4)",
        }
    )
    input_in_cell: str = "input, textarea, select"


@dataclass(frozen=True, slots=True)
class Config:
    excel_file: Path = Path("Opintosuunnitelmat.xlsx")
    log_file: Path = Path("logs/app.log")
    log_level: str = "INFO"
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    selectors: Selectors = field(default_factory=Selectors)
    excel_columns: dict[str, str] = field(
        default_factory=lambda: {
            "osaamistavoite": "Osaamistavoite",
            "laajuus": "Laajuus",
            "suoritustapa": "Suoritustapa / osaaminen hankitaan",
            "suoritusajankohta": "Suoritusajankohta",
        }
    )
    empty_value: str = " "  # lomake ei hyväksy tyhjää kenttää → välilyönti
    separator_row_between_sheets: bool = True
    max_attempts: int = 3
    retry_delay_s: float = 1.0
    wizard: WizardConfig | None = None  # None = kysytään välilehdet numeroina
    teacher: TeacherContact = field(default_factory=TeacherContact)

    @property
    def field_names(self) -> list[str]:
        return list(self.excel_columns)


def load_config(path: Path | str | None = None) -> Config:
    """Lataa asetukset.

    Jos tiedostoa ei anneta eikä ``config.json`` ole olemassa, käytetään oletuksia.
    """
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        if path is not None:
            raise ConfigError(f"Asetustiedostoa ei löydy: {cfg_path}")
        return Config()
    try:
        raw: dict[str, Any] = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Virheellinen JSON asetustiedostossa {cfg_path}: {exc}") from exc
    return config_from_dict(raw, base_dir=cfg_path.resolve().parent)


def config_from_dict(raw: dict[str, Any], *, base_dir: Path | None = None) -> Config:
    """Rakenna Config sanakirjasta. Suhteelliset tiedostopolut ratkaistaan ``base_dir``iin."""
    d = Config()
    ds = Selectors()
    files = raw.get("files", {})

    def _path(value: object, default: Path) -> Path:
        path = Path(str(value)) if value else default
        if base_dir is not None and not path.is_absolute():
            path = base_dir / path
        return path

    browser = raw.get("browser", {})
    selectors = raw.get("selectors", {})
    logging_cfg = raw.get("logging", {})
    retry = raw.get("retry", {})

    return Config(
        excel_file=_path(files.get("excel_file"), d.excel_file),
        log_file=_path(files.get("log_file"), d.log_file),
        log_level=str(logging_cfg.get("level", d.log_level)).upper(),
        browser=BrowserConfig(
            remote_debugging_port=int(browser.get("remote_debugging_port", 9222)),
            user_data_dir=str(browser.get("user_data_dir", "")),
            chrome_path=str(browser.get("chrome_path", "")),
            page_url_contains=str(browser.get("page_url_contains", "")),
            timeout_ms=int(browser.get("timeout_ms", 10_000)),
        ),
        selectors=Selectors(
            table_body=selectors.get("table_body", ds.table_body),
            add_row_button=selectors.get("add_row_button", ds.add_row_button),
            field_cells=dict(selectors.get("field_cells", ds.field_cells)),
            input_in_cell=selectors.get("input_in_cell", ds.input_in_cell),
        ),
        excel_columns=dict(raw.get("excel_columns", d.excel_columns)),
        empty_value=str(raw.get("empty_value", d.empty_value)),
        separator_row_between_sheets=bool(
            raw.get("separator_row_between_sheets", d.separator_row_between_sheets)
        ),
        max_attempts=int(retry.get("max_attempts", d.max_attempts)),
        retry_delay_s=float(retry.get("delay_s", d.retry_delay_s)),
        wizard=WizardConfig.from_dict(raw["wizard"])
        if isinstance(raw.get("wizard"), dict)
        else None,
        teacher=TeacherContact.from_dict(raw["teacher"])
        if isinstance(raw.get("teacher"), dict)
        else TeacherContact(),
    )


def config_to_dict(config: Config, *, base_dir: Path | None = None) -> dict[str, Any]:
    """Muuta Config tallennettavaan muotoon. Polut suhteellisiksi ``base_dir``iin, jos voi."""

    def _rel(path: Path) -> str:
        if base_dir is not None:
            try:
                return str(path.resolve().relative_to(base_dir.resolve()))
            except ValueError:
                pass
        return str(path)

    data: dict[str, Any] = {
        "files": {"excel_file": _rel(config.excel_file), "log_file": _rel(config.log_file)},
        "browser": {
            "remote_debugging_port": config.browser.remote_debugging_port,
            "user_data_dir": config.browser.user_data_dir,
            "chrome_path": config.browser.chrome_path,
            "page_url_contains": config.browser.page_url_contains,
            "timeout_ms": config.browser.timeout_ms,
        },
        "selectors": {
            "table_body": config.selectors.table_body,
            "add_row_button": config.selectors.add_row_button,
            "field_cells": dict(config.selectors.field_cells),
            "input_in_cell": config.selectors.input_in_cell,
        },
        "excel_columns": dict(config.excel_columns),
        "empty_value": config.empty_value,
        "separator_row_between_sheets": config.separator_row_between_sheets,
        "retry": {"max_attempts": config.max_attempts, "delay_s": config.retry_delay_s},
        "logging": {"level": config.log_level},
    }
    data["teacher"] = config.teacher.to_dict()
    if config.wizard is not None:
        data["wizard"] = {
            "main_question": config.wizard.main_question,
            "main_sheets": list(config.wizard.main_sheets),
            "optional_sheets": [
                {"sheet": o.sheet, "question": o.question, "default": o.default}
                for o in config.wizard.optional_sheets
            ],
        }
    return data


def save_config(config: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config_to_dict(config, base_dir=path.resolve().parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_chrome() -> str | None:
    """Etsi Google Chrome nykyiseltä käyttöjärjestelmältä."""
    system = platform.system()
    candidates: list[str] = []
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    elif system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            found = shutil.which(name)
            if found:
                return found
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _quote(value: str) -> str:
    return f'"{value}"' if " " in value else value
