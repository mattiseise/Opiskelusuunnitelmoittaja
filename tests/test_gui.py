"""GUI-savutestit offscreen-Qt:lla (pytest-qt). Ei oikeaa selainta."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QCheckBox

from opiskelusuunnitelmoittaja.config import load_config
from opiskelusuunnitelmoittaja.excel import read_sheet
from opiskelusuunnitelmoittaja.gui.main_window import MainWindow
from opiskelusuunnitelmoittaja.gui.settings_dialog import SettingsDialog
from opiskelusuunnitelmoittaja.gui.worker import FillWorker

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def config_path(tmp_path: Path, excel_file: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Kopio repon config.jsonista, jossa Excel osoittaa testitiedostoon."""
    raw = json.loads((REPO / "config.json").read_text(encoding="utf-8"))
    raw["files"]["excel_file"] = str(excel_file)
    raw["files"]["log_file"] = str(tmp_path / "logs" / "app.log")
    raw["wizard"]["main_sheets"] = ["Ohjelmistokehittäjä", "Kyber", "Puuttuva"]
    raw["wizard"]["optional_sheets"] = [
        {"sheet": "Rikki", "question": "Rikki?", "default": True},
        {"sheet": "Olematon", "question": "Olematon?", "default": True},
    ]
    raw["teacher"] = {"name": "", "email": "", "phone": ""}  # ei yhteystietoja oletuksena
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    # QSettings ei saa vuotaa oikeaan käyttäjäprofiiliin (Windowsissa rekisteriin):
    # ohjataan ini-tiedostoon tmp-kansiossa
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "qt"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "qt"))
    return path


def test_main_window_builds_selection_from_wizard(qtbot, config_path: Path) -> None:
    win = MainWindow(config_path)
    qtbot.addWidget(win)

    # Vain Excelissä olevat pääsuuntaukset näkyvät; "Puuttuva" ei. Viimeisenä vaihtoehto
    # "Ei pääsuuntausta Excelistä" (vain Wilman rivit ja lisävalinnat).
    names = [b.text() for b in win.main_group.buttons()]
    assert names == ["Ohjelmistokehittäjä", "Kyber", "Ei pääsuuntausta Excelistä"]
    assert win.main_group.buttons()[0].isChecked()
    assert win.rb_no_main is win.main_group.buttons()[2]

    # Vain Excelissä oleva lisävalinta näkyy, oletus kyllä
    boxes = [
        win.optional_layout.itemAt(i).widget()  # type: ignore[union-attr]
        for i in range(win.optional_layout.count())
    ]
    boxes = [b for b in boxes if isinstance(b, QCheckBox)]
    assert [str(b.property("sheet")) for b in boxes] == ["Rikki"]
    assert boxes[0].isChecked()

    # Rikki-välilehdeltä puuttuu sarakkeita → esikatselussa vain pääsuuntaus
    assert win.selected_sheet_names() == ["Ohjelmistokehittäjä", "Rikki"]
    assert win.preview.rowCount() == 2
    assert win.preview.item(0, 3).text() == "Ohjelmointi"  # type: ignore[union-attr]
    assert win.preview.item(0, 4).text() == "45"  # type: ignore[union-attr]

    boxes[0].setChecked(False)
    win.main_group.buttons()[1].setChecked(True)
    assert win.selected_sheet_names() == ["Kyber"]
    assert win.preview.rowCount() == 1


def test_manual_selection_mode(qtbot, config_path: Path) -> None:
    win = MainWindow(config_path)
    qtbot.addWidget(win)
    win.manual_toggle.setChecked(True)
    assert win.selected_sheet_names() == []
    assert not win.btn_fill.isEnabled()
    for i in range(win.manual_list.count()):
        if win.manual_list.item(i).text() == "Kyber":
            win.manual_list.item(i).setCheckState(Qt.CheckState.Checked)
    assert win.selected_sheet_names() == ["Kyber"]
    assert win.btn_fill.isEnabled()


def test_preview_row_checkboxes_and_toggle(qtbot, config_path: Path) -> None:
    win = MainWindow(config_path)
    qtbot.addWidget(win)
    assert win.preview.rowCount() == 2
    assert win.checked_row_indices() == [0, 1]
    assert win.header_check.checkState() == Qt.CheckState.Checked

    win.preview.item(1, 1).setCheckState(Qt.CheckState.Unchecked)  # type: ignore[union-attr]
    assert win.checked_row_indices() == [0]
    assert win.preview_label.text().startswith("1 / 2 RIVIÄ")
    assert win.header_check.checkState() == Qt.CheckState.PartiallyChecked
    sheets = win.selected_sheets_for_fill()
    assert [s.name for s in sheets] == ["Ohjelmistokehittäjä"]
    assert [r.values["osaamistavoite"] for r in sheets[0].rows] == ["Ohjelmointi"]

    win.toggle_all_rows()  # ei kaikki valittuna → valitse kaikki
    assert win.checked_row_indices() == [0, 1]
    win.toggle_all_rows()  # kaikki valittuna → poista valinnat
    assert win.checked_row_indices() == []
    assert win.header_check.checkState() == Qt.CheckState.Unchecked
    assert not win.btn_fill.isEnabled()
    assert win.selected_sheets_for_fill() == []


def test_contact_row_in_preview_and_settings(qtbot, config_path: Path) -> None:
    win = MainWindow(config_path)
    qtbot.addWidget(win)
    assert not win.contact_check.isEnabled()  # ei yhteystietoja asetuksissa

    dialog = SettingsDialog(win.config, config_path)
    qtbot.addWidget(dialog)
    dialog.teacher_name.setText("Matti Seise")
    dialog.teacher_email.setText("matti.seise@bc.fi")
    dialog.teacher_phone.setText("041 534 5404")
    dialog.save()
    win.reload_config()

    assert win.contact_check.isEnabled() and win.contact_check.isChecked()
    # välirivi näkyy esikatselussa omana tyhjänä rivinään lähteiden välissä
    assert win.separator_check.isChecked()
    assert win.preview.rowCount() == 4
    assert win.preview.item(2, 2).text() == "Välirivi"  # type: ignore[union-attr]
    assert win.preview.item(2, 3).text() == ""  # type: ignore[union-attr]
    # yhteystietoteksti menee oletuksena Suoritustapa-kenttään (sarake 5)
    last = win.preview.item(3, 5).text()  # type: ignore[union-attr]
    assert last.startswith("Opiskelijalla on henkilökohtainen opintosuunnitelma")
    assert "Matti Seise, sähköposti: matti.seise@bc.fi tai puhelimitse: 041 534 5404" in last
    assert win.preview.item(3, 2).text() == "Yhteystiedot"  # type: ignore[union-attr]
    assert win.preview.item(3, 3).text() == ""  # type: ignore[union-attr]
    assert win.preview.item(3, 4).text() == ""  # type: ignore[union-attr]
    sheets = win.selected_sheets_for_fill()
    assert [s.name for s in sheets] == ["Ohjelmistokehittäjä", "Välirivi", "Yhteystiedot"]
    assert sheets[1].rows[0].is_empty()

    win.separator_check.setChecked(False)
    assert win.preview.rowCount() == 3
    win.contact_check.setChecked(False)
    assert win.preview.rowCount() == 2


def test_time_column_editable_and_applied(qtbot, config_path: Path) -> None:
    win = MainWindow(config_path)
    qtbot.addWidget(win)
    col = win._time_column()
    assert col == 6
    cell = win.preview.item(0, col)
    assert cell is not None and bool(cell.flags() & Qt.ItemFlag.ItemIsEditable)
    assert bool(win.preview.item(0, 3).flags() & Qt.ItemFlag.ItemIsEditable)  # type: ignore[union-attr]
    assert not bool(win.preview.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable)  # type: ignore[union-attr]

    cell.setText("8/2026–5/2027")
    sheets = win.selected_sheets_for_fill()
    assert sheets[0].rows[0].values["suoritusajankohta"] == "8/2026–5/2027"
    assert sheets[0].rows[1].values["suoritusajankohta"] == "syksy 2026"  # Excelin alkuperäinen

    # muokkaus säilyy, kun esikatselu rakennetaan uudelleen (esim. rastin vaihto)
    win.contact_check.setChecked(False)
    win.update_preview()
    assert win.preview.item(0, col).text() == "8/2026–5/2027"  # type: ignore[union-attr]


def test_wilma_rows_edit_reorder_and_replace_mode(qtbot, config_path: Path) -> None:
    from opiskelusuunnitelmoittaja.excel import PlanRow

    win = MainWindow(config_path)
    qtbot.addWidget(win)
    win.separator_check.setChecked(False)
    assert win.mode_append.isChecked()
    assert win.preview.rowCount() == 2  # Excel: Ohjelmointi, Tietoturva

    wilma = [
        PlanRow(
            {"osaamistavoite": "W1", "laajuus": "5", "suoritustapa": "x", "suoritusajankohta": ""}
        ),
        PlanRow(
            {"osaamistavoite": "W2", "laajuus": "6", "suoritustapa": "y", "suoritusajankohta": ""}
        ),
    ]
    win._on_wilma_rows(wilma)
    assert win.mode_replace.isChecked()
    # Wilman haku vaihtaa pääsuuntauksen pois; Excelin suuntauksen voi valita takaisin
    assert win.rb_no_main is not None and win.rb_no_main.isChecked()
    assert win.preview.rowCount() == 2
    assert "2 riviä haettu" in win.wilma_status.text()
    assert win.btn_clear_wilma.isVisibleTo(win)
    win.main_group.buttons()[0].setChecked(True)  # Ohjelmistokehittäjä takaisin
    assert [win.preview.item(r, 2).text() for r in range(4)] == [  # type: ignore[union-attr]
        "Wilma",
        "Wilma",
        "Ohjelmistokehittäjä",
        "Ohjelmistokehittäjä",
    ]  # type: ignore[union-attr]
    assert win.preview_label.text().startswith("4 RIVIÄ · WILMA, OHJELMISTOKEHITTÄJÄ")

    # muokkaa Wilma-rivin osaamistavoitetta ja siirrä Excel-rivi ylimmäksi
    grip = win.preview.item(0, 0)
    assert grip is not None and grip.text() == "⋮⋮"  # tarttumasarake raahaukseen
    win.preview.item(0, 3).setText("W1 muokattu")  # type: ignore[union-attr]
    win.move_row(2, 0)  # sama kuin raahaus riviltä 2 ylimmäksi
    assert win.preview.item(0, 3).text() == "Ohjelmointi"  # type: ignore[union-attr]
    assert win.preview.item(1, 3).text() == "W1 muokattu"  # type: ignore[union-attr]

    sheets = win.selected_sheets_for_fill()
    assert [(s.name, [r.values["osaamistavoite"] for r in s.rows]) for s in sheets] == [
        ("Ohjelmistokehittäjä", ["Ohjelmointi"]),
        ("Wilma", ["W1 muokattu", "W2"]),
        ("Ohjelmistokehittäjä", ["Tietoturva"]),
    ]

    # järjestys ja muokkaus säilyvät, kun esikatselu rakennetaan uudelleen
    win.contact_check.setChecked(True)
    win.update_preview()
    assert win.preview.item(0, 3).text() == "Ohjelmointi"  # type: ignore[union-attr]
    assert win.preview.item(1, 3).text() == "W1 muokattu"  # type: ignore[union-attr]

    win.clear_wilma_rows()
    assert win.preview.rowCount() == 2
    assert win.wilma_status.text().startswith("Ei haettu")
    assert not win.btn_clear_wilma.isVisibleTo(win)


def test_no_main_sheet_option_and_wilma_only(qtbot, config_path: Path) -> None:
    from opiskelusuunnitelmoittaja.excel import PlanRow

    win = MainWindow(config_path)
    qtbot.addWidget(win)
    assert win.rb_no_main is not None
    win.rb_no_main.setChecked(True)
    assert win.selected_sheet_names() == ["Rikki"]  # vain lisävalinta jää
    assert win.preview.rowCount() == 0  # Rikki on rikki → ei rivejä
    assert not win.btn_fill.isEnabled()

    win._on_wilma_rows(
        [
            PlanRow(
                {
                    "osaamistavoite": "W1",
                    "laajuus": "5",
                    "suoritustapa": "",
                    "suoritusajankohta": "",
                }
            )
        ]
    )
    assert win.preview.rowCount() == 1
    assert win.preview.item(0, 2).text() == "Wilma"  # type: ignore[union-attr]
    assert win.btn_fill.isEnabled()
    sheets = win.selected_sheets_for_fill()
    assert [s.name for s in sheets] == ["Wilma"]

    # Wilman rivien poisto palauttaa ensimmäisen pääsuuntauksen
    win.clear_wilma_rows()
    assert win.main_group.buttons()[0].isChecked()
    assert win.selected_sheet_names() == ["Ohjelmistokehittäjä", "Rikki"]


def test_fill_worker_replace_mode_clears_first(qtbot, config_path: Path, excel_file: Path) -> None:
    """replace_existing kulkee workerille (oikea selain testataan test_filler:ssä)."""
    config = load_config(config_path)
    sheets = [read_sheet(excel_file, "Kyber", config.excel_columns)]
    worker = FillWorker(config, sheets, replace_existing=True)
    assert worker.replace_existing is True


def test_settings_dialog_opens_teacher_tab_first(qtbot, config_path: Path) -> None:
    dialog = SettingsDialog(load_config(config_path), config_path)
    qtbot.addWidget(dialog)
    assert dialog.tabs.currentIndex() == 0
    assert dialog.tabs.tabText(0) == "Opettaja"


def test_settings_dialog_roundtrip(qtbot, config_path: Path) -> None:
    config = load_config(config_path)
    dialog = SettingsDialog(config, config_path)
    qtbot.addWidget(dialog)
    dialog.port.setValue(9333)
    dialog.main_sheets.setPlainText("Kyber\nIT-tuki\n")
    dialog._add_optional_row("YTO", "YTO?", True)
    dialog.field_rows["laajuus"][1].setText("Laajuus (osp)")
    dialog.save()

    saved = load_config(config_path)
    assert saved.browser.remote_debugging_port == 9333
    assert saved.wizard is not None
    assert saved.wizard.main_sheets == ["Kyber", "IT-tuki"]
    assert [o.sheet for o in saved.wizard.optional_sheets] == ["Rikki", "Olematon", "YTO"]
    assert saved.wizard.optional_sheets[-1].default is True
    assert saved.excel_columns["laajuus"] == "Laajuus (osp)"
    # Excel-polku säilyi (absoluuttinen, tmp:n ulkopuolella suhteelliseksi ei muuteta väärin)
    assert saved.excel_file.exists()


def test_settings_dialog_rejects_empty_selectors(qtbot, config_path: Path, monkeypatch) -> None:
    config = load_config(config_path)
    dialog = SettingsDialog(config, config_path)
    qtbot.addWidget(dialog)
    dialog.table_body.setText("")
    warned: list[str] = []
    monkeypatch.setattr(
        "opiskelusuunnitelmoittaja.gui.settings_dialog.QMessageBox.warning",
        lambda *a, **k: warned.append(a[1]),
    )
    dialog.save()
    assert warned and dialog.result() == 0


def test_fill_worker_dry_run(qtbot, config_path: Path, excel_file: Path) -> None:
    config = load_config(config_path)
    sheets = [read_sheet(excel_file, "Ohjelmistokehittäjä", config.excel_columns)]
    worker = FillWorker(config, sheets, dry_run=True)
    seen: list[tuple[int, int]] = []
    worker.progress.connect(lambda d, t, _m: seen.append((d, t)))
    with qtbot.waitSignal(worker.finished_ok, timeout=5000) as blocker:
        worker.start()
    summary = blocker.args[0]
    assert summary.successful_rows == 2
    assert seen == [(1, 2), (2, 2)]
    worker.wait(2000)


def test_fill_worker_reports_missing_chrome(qtbot, config_path: Path, excel_file: Path) -> None:
    from dataclasses import replace

    config = load_config(config_path)
    config = replace(config, browser=replace(config.browser, remote_debugging_port=1))
    sheets = [read_sheet(excel_file, "Kyber", config.excel_columns)]
    worker = FillWorker(config, sheets)
    with qtbot.waitSignal(worker.failed, timeout=5000) as blocker:
        worker.start()
    assert "Chrome ei vastaa" in blocker.args[0]
    worker.wait(2000)


# --- täyttötapa, Avaa Excel, asetukset ------------------------------------------


def test_fill_mode_radios_default_hint_and_persistence(qtbot, config_path: Path) -> None:
    from opiskelusuunnitelmoittaja.fillmode import FillMode

    win = MainWindow(config_path)
    qtbot.addWidget(win)
    assert [rb.text() for rb in win.mode_buttons.values()] == [
        "Lisää lomakkeen loppuun",
        "Korvaa lomakkeen nykyiset rivit",
        "Täydennä puuttuvat",
    ]
    assert win.selected_fill_mode() is FillMode.APPEND  # config.jsonin oletus
    assert win.mode_hint.text() == FillMode.APPEND.description

    win.mode_complete.setChecked(True)
    assert win.selected_fill_mode() is FillMode.COMPLETE
    assert win.mode_hint.text() == FillMode.COMPLETE.description
    assert win.settings.value("fill_mode") == "complete"

    # valinta säilyy uuteen ikkunaan (QSettings) ja voittaa configin oletuksen
    win2 = MainWindow(config_path)
    qtbot.addWidget(win2)
    assert win2.selected_fill_mode() is FillMode.COMPLETE


def test_open_excel_button(qtbot, config_path: Path, monkeypatch, tmp_path: Path) -> None:
    win = MainWindow(config_path)
    qtbot.addWidget(win)
    assert win.btn_open_excel.text() == "Avaa Excel"
    opened: list[Path] = []
    monkeypatch.setattr(win, "_open_path", opened.append)
    win.open_excel()
    assert opened == [win.excel_path]

    # puuttuva tiedosto → ilmoitus, ei avausta
    win.excel_path = tmp_path / "ei-ole.xlsx"
    shown: list[str] = []
    monkeypatch.setattr(
        "opiskelusuunnitelmoittaja.gui.main_window.QMessageBox.information",
        lambda *a, **k: shown.append(a[1]),
    )
    win.open_excel()
    assert len(opened) == 1  # ei uutta avausta
    assert shown and "Excel ei löydy" in shown[0]


def test_settings_dialog_fill_mode_roundtrip(qtbot, config_path: Path) -> None:
    from opiskelusuunnitelmoittaja.fillmode import FillMode

    config = load_config(config_path)
    dialog = SettingsDialog(config, config_path)
    qtbot.addWidget(dialog)
    assert dialog.fill_mode.currentData() == "append"
    dialog.fill_mode.setCurrentIndex(list(FillMode).index(FillMode.REPLACE))
    dialog.remove_row_button.setText("[id$='__del']")
    dialog.key_field.setCurrentText("suoritustapa")
    dialog.save()

    saved = load_config(config_path)
    assert saved.fill_mode is FillMode.REPLACE
    assert saved.selectors.remove_row_button == "[id$='__del']"
    assert saved.key_field == "suoritustapa"

    win = MainWindow(config_path)
    qtbot.addWidget(win)
    win.settings.remove("fill_mode")
    win.reload_config()
    assert win.selected_fill_mode() is FillMode.REPLACE


def test_fill_worker_mode_from_flag_and_config(qtbot, config_path: Path, excel_file: Path) -> None:
    from dataclasses import replace

    from opiskelusuunnitelmoittaja.fillmode import FillMode

    config = load_config(config_path)
    sheets = [read_sheet(excel_file, "Kyber", config.excel_columns)]
    assert FillWorker(config, sheets).mode is FillMode.APPEND
    assert FillWorker(config, sheets, replace_existing=True).mode is FillMode.REPLACE
    assert FillWorker(config, sheets, mode=FillMode.COMPLETE).mode is FillMode.COMPLETE
    cfg = replace(config, fill_mode=FillMode.COMPLETE)
    assert FillWorker(cfg, sheets).mode is FillMode.COMPLETE


def test_update_available_link_and_panel_button(qtbot, config_path: Path) -> None:
    from opiskelusuunnitelmoittaja.update import UpdateCheck

    win = MainWindow(config_path)
    qtbot.addWidget(win)
    assert not win.btn_update_available.isVisibleTo(win)  # ei vielä tarkistettu

    win._on_update_checked(UpdateCheck("git", "abc1234", "def5678", available=False))
    assert not win.btn_update_available.isVisibleTo(win)

    check = UpdateCheck("git", "abc1234", "def5678 (2 uutta committia)", available=True)
    win._on_update_checked(check)
    assert win.btn_update_available.isVisibleTo(win)
    assert win.btn_update_available.text() == "Päivitys saatavilla"
    assert win.update_check is check

    # Asetukset → Päivitys saa saman tuloksen ilman uutta hakua
    dialog = SettingsDialog(win.config, config_path, win, tab="Päivitys", update_check=check)
    qtbot.addWidget(dialog)
    assert dialog.tabs.tabText(dialog.tabs.currentIndex()) == "Päivitys"
    panel = dialog.update_panel
    assert panel.btn_update.text() == "Päivitys saatavilla"
    assert panel.btn_update.isEnabled()
    assert panel.status_label.text().startswith("Uusia muutoksia gitissä")

    # ajan tasalla → tavallinen nappi
    panel._on_checked(UpdateCheck("git", "abc1234", "abc1234", available=False))
    assert panel.btn_update.text() == "Päivitä"


def test_delete_row_with_trash_and_restore(qtbot, config_path: Path) -> None:
    from opiskelusuunnitelmoittaja.gui.main_window import DELETE_COL

    win = MainWindow(config_path)
    qtbot.addWidget(win)
    win.separator_check.setChecked(False)
    win.contact_check.setChecked(False)
    assert win.preview.rowCount() == 2
    assert not win.btn_restore.isVisibleTo(win)

    win._on_preview_cell_clicked(0, DELETE_COL)  # roskakori ensimmäisellä rivillä
    assert win.preview.rowCount() == 1
    assert win.preview.item(0, 3).text() == "Tietoturva"  # type: ignore[union-attr]
    assert win.btn_restore.isVisibleTo(win) and "(1)" in win.btn_restore.text()
    assert [r.values["osaamistavoite"] for s in win.selected_sheets_for_fill() for r in s.rows] == [
        "Tietoturva"
    ]

    # poisto säilyy, kun esikatselu rakennetaan uudelleen
    win.update_preview()
    assert win.preview.rowCount() == 1

    win.restore_deleted_rows()
    assert win.preview.rowCount() == 2
    assert not win.btn_restore.isVisibleTo(win)


def test_separator_rows_follow_reordering(qtbot, config_path: Path) -> None:
    from opiskelusuunnitelmoittaja.excel import PlanRow

    win = MainWindow(config_path)
    qtbot.addWidget(win)
    win.contact_check.setChecked(False)
    win.separator_check.setChecked(True)
    win._on_wilma_rows([PlanRow({"osaamistavoite": "W1", "laajuus": "1"})])
    win.main_group.buttons()[0].setChecked(True)
    sources = [win.preview.item(r, 2).text() for r in range(win.preview.rowCount())]  # type: ignore[union-attr]
    assert sources == ["Wilma", "Välirivi", "Ohjelmistokehittäjä", "Ohjelmistokehittäjä"]

    # siirrä Excel-rivi ylimmäksi: välirivi pysyy paikallaan käyttäjän järjestyksessä
    win.move_row(2, 0)
    sources = [win.preview.item(r, 2).text() for r in range(win.preview.rowCount())]  # type: ignore[union-attr]
    assert sources == ["Ohjelmistokehittäjä", "Wilma", "Välirivi", "Ohjelmistokehittäjä"]
    sheets = win.selected_sheets_for_fill()
    assert [s.name for s in sheets] == [
        "Ohjelmistokehittäjä",
        "Wilma",
        "Välirivi",
        "Ohjelmistokehittäjä",
    ]


def test_manual_row_added_below_selection_and_filled(qtbot, config_path: Path) -> None:
    win = MainWindow(config_path)
    qtbot.addWidget(win)
    assert win.preview.rowCount() == 2
    win.preview.selectRow(0)
    idx = win.add_manual_row()
    assert idx == 1  # valitun rivin alle
    assert win.preview.rowCount() == 3
    assert win.preview.item(1, 2).text() == "Oma rivi"  # type: ignore[union-attr]
    assert win.preview_label.text().endswith("OMA RIVI")
    win.preview.item(1, 3).setText("Käsin lisätty")  # type: ignore[union-attr]
    win.preview.item(1, 4).setText("2")  # type: ignore[union-attr]
    sheets = win.selected_sheets_for_fill()
    assert [(s.name, [r.values["osaamistavoite"] for r in s.rows]) for s in sheets] == [
        ("Ohjelmistokehittäjä", ["Ohjelmointi"]),
        ("Oma rivi", ["Käsin lisätty"]),
        ("Ohjelmistokehittäjä", ["Tietoturva"]),
    ]
    # muokkaus ja paikka säilyvät esikatselun uudelleenrakennuksessa
    win.update_preview()
    assert win.preview.item(1, 3).text() == "Käsin lisätty"  # type: ignore[union-attr]

    # ilman valintaa uusi rivi menee loppuun
    win.preview.clearSelection()
    win.preview.setCurrentCell(-1, -1)
    idx = win.add_manual_row()
    assert idx == win.preview.rowCount() - 1
    # roskakori poistaa myös oman rivin
    win.delete_row(idx)
    assert win.preview.rowCount() == 3


def test_update_row_check_and_wilma_student(qtbot, config_path: Path) -> None:
    from opiskelusuunnitelmoittaja.excel import PlanRow

    win = MainWindow(config_path)
    qtbot.addWidget(win)
    assert win.update_row_check.isChecked()  # config.json: fill.update_row = true
    row = PlanRow(
        {"osaamistavoite": "W1", "laajuus": "", "suoritustapa": "", "suoritusajankohta": ""}
    )
    win._on_wilma_rows([row], "Testi Oppilas")
    assert "opiskelijalta Testi Oppilas" in win.wilma_status.text()
    assert win._wilma_student == "Testi Oppilas"
    win.clear_wilma_rows()
    assert win._wilma_student == ""
