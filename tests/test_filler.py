"""Lomaketäytön testit oikealla Chromiumilla paikallista testilomaketta vastaan."""

from __future__ import annotations

from dataclasses import replace

import pytest
from playwright.sync_api import Page

from opiskelusuunnitelmoittaja.config import Config, Selectors
from opiskelusuunnitelmoittaja.excel import PlanRow, Sheet
from opiskelusuunnitelmoittaja.filler import FormFiller
from opiskelusuunnitelmoittaja.fillmode import FillMode

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


# --- täyttötavat: korvaa / täydennä --------------------------------------------


def _prefill(page: Page, *rows: PlanRow) -> None:
    """Simuloi lomakkeella jo olevaa opintosuunnitelmaa (lisäystilassa, ilman väliriviä).

    lomake.html: ensimmäinen (valmis) rivi on ilman poistonappia kuten Wilman tallennettu
    rivi, lisätyt rivit saavat poistonapin.
    """
    cfg = replace(CFG, separator_row_between_sheets=False)
    FormFiller(page, cfg).process_sheets([Sheet("Vanha", list(rows))])


def test_replace_mode_overwrites_in_place_and_adds_more(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    _prefill(page, _row("Vanha 1", "1"), _row("Vanha 2", "2"))
    assert len(_table_values(page)) == 2

    cfg = replace(CFG, separator_row_between_sheets=False)
    summary = FormFiller(page, cfg, mode=FillMode.REPLACE).process_sheets(
        [Sheet("A", [_row("Uusi 1", "10"), _row("Uusi 2", "20"), _row("Uusi 3", "30")])]
    )
    assert summary.mode is FillMode.REPLACE
    assert summary.successful_rows == 3
    assert summary.removed_rows == 1  # lisätty rivi 2 poistettiin napilla, rivi 1 tyhjennettiin
    assert summary.cleared_rows == 0  # loppuun ei jäänyt tyhjiä
    values = _table_values(page)
    assert [v[0] for v in values] == ["Uusi 1", "Uusi 2", "Uusi 3"]
    assert values[0][1] == "10"


def test_replace_mode_reports_trailing_empty_rows(
    page: Page, lomake_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    page.goto(lomake_url)
    _prefill(page, _row("Vanha 1", "1"), _row("Vanha 2", "2"), _row("Vanha 3", "3"))

    cfg = replace(CFG, selectors=replace(CFG.selectors, remove_row_button=""))
    with caplog.at_level("WARNING", logger="suunnitelmoittaja.filler"):
        summary = FormFiller(page, cfg, mode=FillMode.REPLACE).process_sheets(
            [Sheet("A", [_row("Uusi 1", "10")])]
        )
    assert summary.removed_rows == 0
    assert summary.cleared_rows == 2  # ilman poistonappia kaikki jäävät, kaksi tyhjäksi
    values = _table_values(page)
    assert [v[0] for v in values] == ["Uusi 1", "", ""]
    assert any("jäi 2 tyhjää riviä" in r.message for r in caplog.records)


def test_replace_mode_removes_added_rows_with_default_selector(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    _prefill(page, _row("Vanha 1", "1"), _row("Vanha 2", "2"), _row("Vanha 3", "3"))

    summary = FormFiller(page, CFG, mode=FillMode.REPLACE).process_sheets(
        [Sheet("A", [_row("Uusi 1", "10")])]
    )
    assert summary.removed_rows == 2
    assert summary.cleared_rows == 0
    assert _table_values(page) == [["Uusi 1", "10", "Joustava", " "]]


def test_replace_mode_with_nothing_to_fill(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    _prefill(page, _row("Vanha 1", "1"), _row("Vanha 2", "2"), _row("Vanha 3", "3"))
    summary = FormFiller(page, CFG, mode=FillMode.REPLACE).process_sheets([Sheet("A", [])])
    assert summary.removed_rows == 2
    assert summary.cleared_rows == 1
    assert _table_values(page) == [["", "", "", ""]]


def test_replace_mode_separator_and_empty_form(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    _prefill(page, _row("Vanha 1", "1"), _row("Vanha 2", "2"))
    summary = FormFiller(page, CFG, mode=FillMode.REPLACE).process_sheets(
        [Sheet("A", [_row("A1", "1")]), Sheet("B", [_row("B1", "2")])]
    )
    assert summary.successful_rows == 2
    assert [v[0] for v in _table_values(page)] == ["A1", "", "B1"]
    assert summary.cleared_rows == 0  # välirivi ei ole ylijäämä

    page.goto(lomake_url)
    summary = FormFiller(page, CFG, mode=FillMode.REPLACE).process_sheets(
        [Sheet("A", [_row("A1", "1"), _row("A2", "2")])]
    )
    assert [v[0] for v in _table_values(page)] == ["A1", "A2"]


def test_complete_skips_rows_already_on_form(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    # lomakkeella: Ohjelmointi eri laajuudella, Tietoturva eri kirjainkoolla ja välilyönneillä
    _prefill(page, _row("Ohjelmointi", "99", "Vanha tapa"), _row("  tietoturva ", "30"))

    cfg = replace(CFG, separator_row_between_sheets=False)
    messages: list[str] = []
    filler = FormFiller(page, cfg, mode=FillMode.COMPLETE, progress=messages.append)
    summary = filler.process_sheets(
        [
            Sheet("A", [_row("Ohjelmointi", "45"), _row("Tietoturva", "30")]),
            Sheet("B", [_row("Uusi tavoite", "5"), _row("Uusi tavoite", "5")]),  # duplikaatti
        ]
    )
    assert summary.mode is FillMode.COMPLETE
    assert summary.skipped_rows == 3
    assert summary.successful_rows == 1
    assert summary.total_rows == 1
    a = next(s for s in summary.sheets if s.sheet_name == "A")
    assert a.skipped == ["Ohjelmointi", "Tietoturva"]
    assert a.total_rows == 0
    values = _table_values(page)
    assert len(values) == 3
    assert values[0] == ["Ohjelmointi", "99", "Vanha tapa", " "]  # ei koskettu
    assert values[2][0] == "Uusi tavoite"
    assert any("on jo lomakkeella" in m for m in messages)


def test_complete_adds_no_separator_for_fully_present_sheet(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    _prefill(page, _row("A1", "1"))

    summary = FormFiller(page, CFG, mode=FillMode.COMPLETE).process_sheets(
        [Sheet("A", [_row("A1", "1")]), Sheet("B", [_row("B1", "2")])]
    )
    assert summary.skipped_rows == 1
    assert summary.successful_rows == 1
    assert [v[0] for v in _table_values(page)] == ["A1", "B1"]  # ei väliriviä


def test_complete_on_empty_form_fills_everything(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    summary = FormFiller(page, CFG, mode=FillMode.COMPLETE).process_sheets(
        [Sheet("A", [_row("A1", "1"), _row("A2", "2")])]
    )
    assert summary.skipped_rows == 0
    assert summary.successful_rows == 2
    assert [v[0] for v in _table_values(page)] == ["A1", "A2"]


def test_mode_defaults_from_config(page: Page, lomake_url: str) -> None:
    page.goto(lomake_url)
    cfg = replace(CFG, fill_mode=FillMode.COMPLETE)
    assert FormFiller(page, cfg).mode is FillMode.COMPLETE
    assert FormFiller(page, cfg, mode=FillMode.REPLACE).mode is FillMode.REPLACE
    dry = FormFiller(None, cfg, dry_run=True, mode=FillMode.REPLACE)
    assert dry.process_sheets([Sheet("A", [_row("A1", "1")])]).successful_rows == 1


# --- Wilman lomakkeen rakennekopio -------------------------------------------------


def test_wilma_append_adds_rows_with_remove_button(page: Page, wilma_url: str) -> None:
    page.goto(wilma_url)
    cfg = replace(CFG, separator_row_between_sheets=False)
    summary = FormFiller(page, cfg).process_sheets([Sheet("A", [_row("Uusi", "5")])])
    assert summary.successful_rows == 1
    values = _table_values(page)
    assert len(values) == 5  # 4 tallennettua + 1 uusi, viimeinen rivi ei ollut tyhjä
    assert values[4] == ["Uusi", "5", "Joustava", " "]
    assert page.locator("#rows tr").nth(4).locator("[id$='__remove']").count() == 1
    assert page.locator("#rows tr").nth(0).locator("[id$='__remove']").count() == 0
    assert _table_values(page, "#meta-rows") == [["14.4.2025", "Opettaja Testi"]]


def test_wilma_replace_clears_saved_rows_and_removes_added(page: Page, wilma_url: str) -> None:
    page.goto(wilma_url)
    # opettaja on lisännyt yhden rivin tässä istunnossa (napillinen), sitten korvaa 2 rivillä
    FormFiller(page, replace(CFG, separator_row_between_sheets=False)).process_sheets(
        [Sheet("Lisätty", [_row("Kesken jäänyt", "1")])]
    )
    assert len(_table_values(page)) == 5

    summary = FormFiller(page, CFG, mode=FillMode.REPLACE).process_sheets(
        [Sheet("A", [_row("Uusi 1", "10"), _row("Uusi 2", "20")])]
    )
    assert summary.successful_rows == 2
    assert summary.removed_rows == 1  # lisätty rivi poistettiin napista
    assert summary.cleared_rows == 2  # tallennetut rivit 3 ja 4 jäivät tyhjiksi
    values = _table_values(page)
    assert [v[0] for v in values] == ["Uusi 1", "Uusi 2", "", ""]
    assert values[2] == ["", "", "", ""]


def test_wilma_complete_matches_osp_suffix_and_prefix(page: Page, wilma_url: str) -> None:
    page.goto(wilma_url)
    cfg = replace(CFG, separator_row_between_sheets=False)
    summary = FormFiller(page, cfg, mode=FillMode.COMPLETE).process_sheets(
        [
            Sheet(
                "YTO",
                [
                    _row("Taide ja luova ilmaisu", "1"),  # lomakkeella "… 1osp"
                    _row("Äidinkieli 4", "1"),  # lomakkeella "Äidinkieli 4 1osp"
                    _row("Äidinkieli 3", "1"),  # puuttuu
                    _row("Terveystieto", "1"),  # täsmälleen
                    _row("Fysiikka", "1"),  # puuttuu (lyhyt, ei alkuosavertailua)
                    _row("Ohjelmoinnin perusteet, verkkokurssi", "15"),  # alkuosa vastaa
                ],
            )
        ]
    )
    assert summary.skipped_rows == 4
    assert summary.sheets[0].skipped == [
        "Taide ja luova ilmaisu",
        "Äidinkieli 4",
        "Terveystieto",
        "Ohjelmoinnin perusteet, verkkokurssi",
    ]
    assert summary.successful_rows == 2
    values = _table_values(page)
    assert [v[0] for v in values[4:]] == ["Äidinkieli 3", "Fysiikka"]
    assert values[0][0] == "Ohjelmoinnin perusteet"  # ei koskettu


def test_norm_and_find_match() -> None:
    from opiskelusuunnitelmoittaja.filler import _find_match, _norm

    assert _norm("Taide ja luova ilmaisu 1osp") == "taide ja luova ilmaisu"
    assert _norm("Terveystieto (1 osp)") == "terveystieto"
    assert _norm("  Äidinkieli   4 1 osp ") == "äidinkieli 4"
    assert _norm("Matematiikka 2,5 osp:") == "matematiikka"
    assert _norm("Ohjelmointi 2") == "ohjelmointi 2"  # numero ilman osp:tä säilyy
    existing = ["Fysiikka 1osp", "Fysiikka 2 1osp", "Ohjelmoinnin perusteet"]
    assert _find_match("fysiikka", existing) == "Fysiikka 1osp"
    assert _find_match("Fysiikka 2", existing) == "Fysiikka 2 1osp"
    assert _find_match("Fysiikka 3", existing) is None
    assert _find_match("Ohjelmoinnin perusteet, verkkokurssi", existing) == (
        "Ohjelmoinnin perusteet"
    )
    assert _find_match("Ohjelmointi", existing) is None  # alkuosa, mutta eri sana
    assert _find_match("", existing) is None
