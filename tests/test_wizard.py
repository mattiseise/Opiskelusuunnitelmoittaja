from __future__ import annotations

from collections.abc import Iterator

import pytest

from opiskelusuunnitelmoittaja.config import config_from_dict
from opiskelusuunnitelmoittaja.wizard import (
    OptionalSheet,
    WizardCancelled,
    WizardConfig,
    run_wizard,
)

AVAILABLE = ["Ohjelmistokehittäjä", "Kyber", "IT-tuki", "Lukio", "Väylä", "YTO"]
WIZARD = WizardConfig(
    main_sheets=["Ohjelmistokehittäjä", "Kyber", "IT-tuki"],
    optional_sheets=[
        OptionalSheet("Lukio", "Kaksoistutkinto?", default=False),
        OptionalSheet("YTO", "YTO?", default=True),
        OptionalSheet("Väylä", "Väylä?", default=False),
    ],
)


def _scripted(*answers: str):
    it: Iterator[str] = iter(answers)

    def ask(_prompt: str) -> str:
        return next(it)

    return ask


def test_main_plus_lukio_and_yto() -> None:
    chosen = run_wizard(WIZARD, AVAILABLE, ask=_scripted("2", "k", "k", "e"), say=lambda _: None)
    assert chosen == ["Kyber", "Lukio", "YTO"]


def test_defaults_apply_on_empty_answer() -> None:
    # tyhjä vastaus → Lukio ei (oletus), YTO kyllä (oletus), Väylä ei (oletus)
    chosen = run_wizard(WIZARD, AVAILABLE, ask=_scripted("1", "", "", ""), say=lambda _: None)
    assert chosen == ["Ohjelmistokehittäjä", "YTO"]


def test_main_by_name_case_insensitive() -> None:
    chosen = run_wizard(
        WIZARD, AVAILABLE, ask=_scripted("it-tuki", "e", "e", "k"), say=lambda _: None
    )
    assert chosen == ["IT-tuki", "Väylä"]


def test_invalid_then_valid_answers() -> None:
    said: list[str] = []
    chosen = run_wizard(
        WIZARD, AVAILABLE, ask=_scripted("9", "x", "3", "ehkä", "e", "e", "e"), say=said.append
    )
    assert chosen == ["IT-tuki"]
    assert any("Virheellinen" in s for s in said)
    assert any("Vastaa k" in s for s in said)


def test_empty_main_answer_cancels() -> None:
    with pytest.raises(WizardCancelled):
        run_wizard(WIZARD, AVAILABLE, ask=_scripted(""), say=lambda _: None)


def test_missing_sheets_are_skipped() -> None:
    said: list[str] = []
    chosen = run_wizard(WIZARD, ["Kyber", "YTO"], ask=_scripted("1", "e"), say=said.append)
    assert chosen == ["Kyber"]  # YTO vastattiin e; Lukio ja Väylä ohitettiin kysymättä
    assert any("puuttuvat Excelistä" in s for s in said)


def test_no_main_sheets_available_raises() -> None:
    with pytest.raises(WizardCancelled, match="pääsuuntauksen"):
        run_wizard(WIZARD, ["YTO"], ask=_scripted("1"), say=lambda _: None)


def test_wizard_parsed_from_config() -> None:
    cfg = config_from_dict(
        {
            "wizard": {
                "main_sheets": ["A", "B"],
                "optional_sheets": [{"sheet": "C", "question": "C?", "default": True}, {"bad": 1}],
            }
        }
    )
    assert cfg.wizard is not None
    assert cfg.wizard.main_sheets == ["A", "B"]
    assert cfg.wizard.optional_sheets == [OptionalSheet("C", "C?", default=True)]


def test_no_wizard_in_config() -> None:
    assert config_from_dict({}).wizard is None
