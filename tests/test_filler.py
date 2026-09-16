"""Lomaketäytön testit oikealla Chromiumilla paikallista testilomaketta vastaan."""

from __future__ import annotations

from dataclasses import replace

from playwright.sync_api import Page

from opiskelusuunnitelmoittaja.config import Config, Selectors
from opiskelusuunnitelmoittaja.excel import PlanRow, Sheet
from opiskelusuunnitelmoittaja.filler import FormFiller

CFG = replace(Config(), retry_delay_s=0.05, max_attempts=2)


def _row(tavoite: str, laajuus: str, tapa: str = "Joustava", aika: str = "") -> PlanRow:
    return PlanRow(
        {
            "osaamistavoite": tavoite,
            "laajuus": laajuus,
            "suoritustapa": tapa,
            "suoritusajankohta": aika,
        }
    )


def _table_values(page: Page) -> list[list[str]]:
    return page.evaluate(
        "() => [...document.querySelectorAll('#rows > tr')]"
        ".map(tr => [...tr.querySelectorAll('input')].map(i => i.value))"
    )


def test_fill_new_row_adds_and_fills(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    filler = FormFiller(page, CFG)
    filler.fill_new_row(_row("Ohjelmointi", "45"))
    filler.fill_new_row(_row("Tietoturva", "30", "Lähiopetus", "syksy 2026"))

    assert _table_values(page) == [
        ["Ohjelmointi", "45", "Joustava", " "],  # tyhjä → empty_value (välilyönti)
        ["Tietoturva", "30", "Lähiopetus", "syksy 2026"],
    ]


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
    assert _table_values(page) == []


def test_missing_add_button_is_reported_per_row(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    cfg = replace(
        CFG,
        browser=replace(CFG.browser, timeout_ms=300),
        selectors=replace(Selectors(), add_row_button="#ei-ole"),
    )
    summary = FormFiller(page, cfg).process_sheets([Sheet("A", [_row("A1", "1")])])
    assert summary.failed_rows == 1
    assert "rivin lisäys" in summary.sheets[0].errors[0]


def test_progress_callback_is_called(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    messages: list[str] = []
    FormFiller(page, CFG, progress=messages.append).process_sheet(
        Sheet("A", [_row("A1", "1"), _row("A2", "2")])
    )
    assert messages == ["  A: rivi 1/2", "  A: rivi 2/2"]
