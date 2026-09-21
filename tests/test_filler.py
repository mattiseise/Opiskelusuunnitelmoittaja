"""Lomaketäytön testit oikealla Chromiumilla paikallista testilomaketta vastaan."""

from __future__ import annotations

from dataclasses import replace

import pytest
from playwright.sync_api import Page

from opiskelusuunnitelmoittaja.config import Config, Selectors
from opiskelusuunnitelmoittaja.excel import PlanRow, Sheet
from opiskelusuunnitelmoittaja.filler import FormFiller

# Sama valitsin kuin repon config.jsonissa: sivulla on kaksi taulukkoa, osutaan oikeaan.
CFG = replace(
    Config(),
    retry_delay_s=0.05,
    max_attempts=2,
    selectors=replace(Selectors(), table_body='table:has(th:has-text("Osaamistavoite")) tbody'),
)


def _row(tavoite: str, laajuus: str, tapa: str = "Joustava", aika: str = "") -> PlanRow:
    return PlanRow(
        {
            "osaamistavoite": tavoite,
            "laajuus": laajuus,
            "suoritustapa": tapa,
            "suoritusajankohta": aika,
        }
    )


def _table_values(page: Page, tbody: str = "#rows") -> list[list[str]]:
    return page.evaluate(
        "id => [...document.querySelectorAll(id + ' > tr')]"
        ".map(tr => [...tr.querySelectorAll('input')].map(i => i.value))",
        tbody,
    )


def test_fill_new_row_adds_and_fills(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    filler = FormFiller(page, CFG)
    filler.fill_new_row(_row("Ohjelmointi", "45"))
    filler.fill_new_row(_row("Tietoturva", "30", "Lähiopetus", "syksy 2026"))

    assert _table_values(page) == [
        ["Ohjelmointi", "45", "Joustava", " "],  # valmis tyhjä rivi käytettiin; tyhjä → " "
        ["Tietoturva", "30", "Lähiopetus", "syksy 2026"],
    ]
    # Pvm & päivittäjä -taulukkoon ei kosketa
    assert _table_values(page, "#meta-rows") == [["", ""]]


def test_process_sheets_adds_separator_row(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    sheets = [
        Sheet("A", [_row("A1", "1"), _row("A2", "2")]),
        Sheet("B", [_row("B1", "3")]),
    ]
    summary = FormFiller(page, CFG).process_sheets(sheets)

    assert summary.total_rows == 3
    assert summary.successful_rows == 3
    assert summary.failed_rows == 0
    values = _table_values(page)
    assert len(values) == 4  # 2 + välirivi + 1
    assert values[2] == ["", "", "", ""]
    assert values[3][0] == "B1"


def test_process_sheets_without_separator(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    cfg = replace(CFG, separator_row_between_sheets=False)
    FormFiller(page, cfg).process_sheets(
        [Sheet("A", [_row("A1", "1")]), Sheet("B", [_row("B1", "2")])]
    )
    assert len(_table_values(page)) == 2


def test_dry_run_touches_nothing(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    summary = FormFiller(page, CFG, dry_run=True).process_sheets([Sheet("A", [_row("A1", "1")])])
    assert summary.successful_rows == 1
    assert _table_values(page) == [["", "", "", ""]]


def test_missing_add_button_is_reported_per_row(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    cfg = replace(
        CFG,
        browser=replace(CFG.browser, timeout_ms=300),
        selectors=replace(Selectors(), add_row_button="#ei-ole"),
    )
    # 1. rivi menee valmiiseen tyhjään riviin, 2. vaatii lisäysnapin → epäonnistuu
    summary = FormFiller(page, cfg).process_sheets([Sheet("A", [_row("A1", "1"), _row("A2", "2")])])
    assert summary.successful_rows == 1
    assert summary.failed_rows == 1
    assert "rivin lisäys" in summary.sheets[0].errors[0]


def test_prefilled_row_is_not_reused(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    page.locator("#rows input").first.fill("jo täytetty")
    FormFiller(page, CFG).fill_new_row(_row("A1", "1"))
    values = _table_values(page)
    assert len(values) == 2
    assert values[0][0] == "jo täytetty"
    assert values[1][0] == "A1"


def test_generic_selector_hits_first_table_with_warning(
    page: Page, lomake_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    page.goto(lomake_url)
    cfg = replace(CFG, selectors=replace(Selectors(), table_body="main form table tbody"))
    with caplog.at_level("WARNING", logger="suunnitelmoittaja.filler"):
        FormFiller(page, cfg).fill_new_row(_row("A1", "1"))
    assert _table_values(page)[0][0] == "A1"
    assert _table_values(page, "#meta-rows") == [["", ""]]
    assert any("osuu 2 taulukkoon" in r.message for r in caplog.records)


def test_progress_callback_is_called(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    messages: list[str] = []
    FormFiller(page, CFG, progress=messages.append).process_sheet(
        Sheet("A", [_row("A1", "1"), _row("A2", "2")])
    )
    assert messages == ["  A: rivi 1/2", "  A: rivi 2/2"]


def test_read_rows_and_clear_rows(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    filler = FormFiller(page, CFG)
    filler.fill_new_row(_row("A1", "1", "Tapa", "8/2026"))
    filler.fill_new_row(_row("A2", "2"))
    filler.fill_new_row(_row("A3", "3"))
    assert len(_table_values(page)) == 3

    rows = FormFiller(page, CFG).read_rows()
    assert [r.values["osaamistavoite"] for r in rows] == ["A1", "A2", "A3"]
    assert rows[0].values["suoritusajankohta"] == "8/2026"
    assert rows[1].values["suoritusajankohta"] == ""  # välilyönti trimmataan

    clearer = FormFiller(page, CFG)
    removed = clearer.clear_rows()
    assert removed == 2  # ensimmäisellä rivillä ei ole poistonappia
    assert _table_values(page) == [["", "", "", ""]]
    # tyhjennetty rivi käytetään uudelleen
    clearer.fill_new_row(_row("B1", "9"))
    assert _table_values(page)[0][0] == "B1" and len(_table_values(page)) == 1


def test_saved_form_append_uses_trailing_empty_row(page: Page, tallennettu_url: str) -> None:
    """Lisäystila tallennetulla lomakkeella: vanhat rivit säilyvät, tyhjä viimeinen käytetään."""
    page.goto(tallennettu_url)
    filler = FormFiller(page, CFG)
    filler.fill_new_row(_row("Uusi 1", "5"))
    filler.fill_new_row(_row("Uusi 2", "6"))
    values = _table_values(page)
    assert [v[0] for v in values] == ["Vanha 1", "Vanha 2", "Vanha 3", "Uusi 1", "Uusi 2"]
    assert page.locator("#count").input_value() == "5"
    assert _table_values(page, "#meta-rows") == [["", ""]]


def test_saved_form_replace_overwrites_in_place(page: Page, tallennettu_url: str) -> None:
    """Korvaustila: tallennettuja rivejä ei voi poistaa → tyhjennetään ja kirjoitetaan yli."""
    page.goto(tallennettu_url)
    rows = FormFiller(page, CFG).read_rows()
    assert [r.values["osaamistavoite"] for r in rows] == ["Vanha 1", "Vanha 2", "Vanha 3"]

    filler = FormFiller(page, CFG)
    assert filler.clear_rows() == 0  # mitään ei voitu poistaa napilla
    assert _table_values(page) == [[""] * 4] * 4

    filler.fill_new_row(_row("A", "1"))
    filler.fill_new_row(_row("B", "2"))
    assert [v[0] for v in _table_values(page)] == ["A", "B", "", ""]

    # tyhjät loppuvat → lisäysnappi
    filler.fill_new_row(_row("C", "3"))
    filler.fill_new_row(_row("D", "4"))
    filler.fill_new_row(_row("E", "5"))
    assert [v[0] for v in _table_values(page)] == ["A", "B", "C", "D", "E"]
    assert page.locator("#count").input_value() == "5"

    # toinen korvaus samalla sivulla: lisätty rivi E poistetaan napilla, loput tyhjennetään
    second = FormFiller(page, CFG)
    assert second.clear_rows() == 1
    assert [v[0] for v in _table_values(page)] == ["", "", "", ""]


def test_saved_form_replace_with_separator(page: Page, tallennettu_url: str) -> None:
    """Välirivi kuluttaa korvaustilassa tyhjän rivin eikä lisää uutta."""
    page.goto(tallennettu_url)
    filler = FormFiller(page, CFG)
    filler.clear_rows()
    filler.process_sheets([Sheet("A", [_row("A1", "1")]), Sheet("B", [_row("B1", "2")])])
    assert [v[0] for v in _table_values(page)] == ["A1", "", "B1", ""]
