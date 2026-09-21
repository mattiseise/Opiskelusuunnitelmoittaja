"""Täyttötapa: miten lomakkeella jo olevat rivit käsitellään."""

from __future__ import annotations

from enum import StrEnum


class FillMode(StrEnum):
    APPEND = "append"  # lisää rivit loppuun, olemassa oleviin ei kosketa
    REPLACE = "replace"  # korvaa olemassa oleva opintosuunnitelma
    COMPLETE = "complete"  # täydennä puuttuvat: lisää vain rivit, joita ei vielä ole

    @classmethod
    def parse(cls, value: object, default: FillMode | None = None) -> FillMode:
        text = str(value or "").strip().casefold()
        for mode in cls:
            if text in {mode.value, mode.label.casefold(), mode.short.casefold()}:
                return mode
        if default is not None:
            return default
        raise ValueError(
            f"tuntematon täyttötapa {value!r}; vaihtoehdot: {', '.join(m.value for m in cls)}"
        )

    @property
    def label(self) -> str:
        return LABELS[self]

    @property
    def short(self) -> str:
        return SHORT[self]

    @property
    def description(self) -> str:
        return DESCRIPTIONS[self]


LABELS: dict[FillMode, str] = {
    FillMode.APPEND: "Lisää loppuun",
    FillMode.REPLACE: "Korvaa olemassa oleva opintosuunnitelma",
    FillMode.COMPLETE: "Täydennä puuttuvat",
}
SHORT: dict[FillMode, str] = {
    FillMode.APPEND: "lisää",
    FillMode.REPLACE: "korvaa",
    FillMode.COMPLETE: "täydennä",
}
DESCRIPTIONS: dict[FillMode, str] = {
    FillMode.APPEND: "Lomakkeen nykyisiin riveihin ei kosketa; uudet rivit tulevat niiden perään.",
    FillMode.REPLACE: (
        "Lomakkeen nykyiset rivit kirjoitetaan yli järjestyksessä. Ylimääräiset rivit "
        "poistetaan, jos poistonappi on asetuksissa; muuten ne tyhjennetään."
    ),
    FillMode.COMPLETE: (
        "Lisätään vain ne rivit, joiden osaamistavoitetta ei vielä ole lomakkeella. "
        "Nykyisiin riveihin ei kosketa."
    ),
}
