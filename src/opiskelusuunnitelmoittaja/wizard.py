"""Ohjattu kysely: mitä opiskelijalle laitetaan.

Kysyy ensin pääsuuntauksen (yksi välilehti) ja sen jälkeen kyllä/ei-kysymyksinä
lisävälilehdet (esim. kaksoistutkinto → Lukio, YTO-opinnot → YTO). Kysymykset tulevat
asetuksista, joten Excelin välilehtiä voi lisätä ilman koodimuutoksia.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

Prompter = Callable[[str], str]

YES = {"k", "kyllä", "kylla", "y", "yes", "j", "joo"}
NO = {"e", "ei", "n", "no"}


@dataclass(frozen=True, slots=True)
class OptionalSheet:
    sheet: str
    question: str
    default: bool = False


@dataclass(frozen=True, slots=True)
class WizardConfig:
    main_question: str = "Mikä on opiskelijan pääsuuntaus?"
    main_sheets: list[str] = field(default_factory=list)
    optional_sheets: list[OptionalSheet] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> WizardConfig:
        optional: list[OptionalSheet] = []
        for item in raw.get("optional_sheets", []) or []:
            if not isinstance(item, dict):
                continue
            sheet = str(item.get("sheet", "")).strip()
            if not sheet:
                continue
            optional.append(
                OptionalSheet(
                    sheet=sheet,
                    question=str(item.get("question") or f"Lisätäänkö {sheet}?"),
                    default=bool(item.get("default", False)),
                )
            )
        main_sheets = [str(s) for s in (raw.get("main_sheets", []) or [])]
        return cls(
            main_question=str(raw.get("main_question") or cls().main_question),
            main_sheets=main_sheets,
            optional_sheets=optional,
        )


class WizardCancelled(Exception):
    """Käyttäjä keskeytti kyselyn."""


def run_wizard(
    wizard: WizardConfig,
    available: list[str],
    *,
    ask: Prompter = input,
    say: Callable[[str], None] = print,
) -> list[str]:
    """Kysy valinnat ja palauta täytettävät välilehdet järjestyksessä.

    Vain Excelissä oikeasti olevat välilehdet tarjotaan. Nostaa WizardCancelled,
    jos käyttäjä vastaa tyhjää pääsuuntaukseen tai keskeyttää.
    """
    mains = [s for s in wizard.main_sheets if s in available]
    missing = [s for s in wizard.main_sheets if s not in available]
    if missing:
        say(f"(Huom. asetuksissa mainitut välilehdet puuttuvat Excelistä: {', '.join(missing)})")
    if not mains:
        raise WizardCancelled(
            "Yhtään pääsuuntauksen välilehteä ei löydy Excelistä. Tarkista config.json → wizard."
        )

    chosen: list[str] = []

    say(wizard.main_question)
    for i, name in enumerate(mains, start=1):
        say(f"  {i}: {name}")
    while True:
        answer = ask("Valinta (numero tai nimi, tyhjä = peruuta): ").strip()
        if not answer:
            raise WizardCancelled("Ei valintaa.")
        if answer.isdigit() and 1 <= int(answer) <= len(mains):
            chosen.append(mains[int(answer) - 1])
            break
        match = next((m for m in mains if m.casefold() == answer.casefold()), None)
        if match:
            chosen.append(match)
            break
        say("Virheellinen valinta, yritä uudelleen.")

    for opt in wizard.optional_sheets:
        if opt.sheet not in available:
            say(f"(Välilehteä '{opt.sheet}' ei ole Excelissä, ohitetaan kysymys)")
            continue
        if _ask_yes_no(ask, say, opt.question, default=opt.default):
            chosen.append(opt.sheet)

    say("")
    say("Täytetään välilehdet: " + ", ".join(chosen))
    return chosen


def ask_yes_no(
    question: str,
    *,
    default: bool,
    ask: Prompter = input,
    say: Callable[[str], None] = print,
) -> bool:
    """Kyllä/ei-kysymys konsolissa; tyhjä vastaus palauttaa oletuksen."""
    return _ask_yes_no(ask, say, question, default=default)


def _ask_yes_no(ask: Prompter, say: Callable[[str], None], question: str, *, default: bool) -> bool:
    hint = "[K/e]" if default else "[k/E]"
    while True:
        answer = ask(f"{question} {hint} ").strip().casefold()
        if not answer:
            return default
        if answer in YES:
            return True
        if answer in NO:
            return False
        say("Vastaa k (kyllä) tai e (ei).")
