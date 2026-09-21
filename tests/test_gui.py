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

    # Vain Excelissä olevat pääsuuntaukset näkyvät; "Puuttuva" ei
    names = [b.text() for b in win.main_group.buttons()]
    assert names == ["Ohjelmistokehittäjä", "Kyber"]
    assert win.main_group.buttons()[0].isChecked()

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
    assert win.preview.item(0, 2).text() == "Ohjelmointi"  # type: ignore[union-attr]
    assert win.preview.item(0, 3).text() == "45"  # type: ignore[union-attr]

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

    win.preview.item(1, 0).setCheckState(Qt.CheckState.Unchecked)  # type: ignore[union-attr]
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
    assert win.preview.rowCount() == 3
    last = win.preview.item(2, 2).text()  # type: ignore[union-attr]
    assert last.startswith("Opiskelijalla on henkilökohtainen opintosuunnitelma")
    assert "Matti Seise, sähköposti: matti.seise@bc.fi tai puhelimitse: 041 534 5404" in last
    assert win.preview.item(2, 1).text() == "Yhteystiedot"  # type: ignore[union-attr]
    assert win.preview.item(2, 3).text() == ""  # type: ignore[union-attr]
    sheets = win.selected_sheets_for_fill()
    assert [s.name for s in sheets][-1] == "Yhteystiedot"

    win.contact_check.setChecked(False)
    assert win.preview.rowCount() == 2


def test_time_column_editable_and_applied(qtbot, config_path: Path) -> None:
    win = MainWindow(config_path)
    qtbot.addWidget(win)
    col = win._time_column()
    assert col == 5
    cell = win.preview.item(0, col)
    assert cell is not None and bool(cell.flags() & Qt.ItemFlag.ItemIsEditable)
    assert not bool(win.preview.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable)  # type: ignore[union-attr]

    cell.setText("8/2026–5/2027")
    sheets = win.selected_sheets_for_fill()
    assert sheets[0].rows[0].values["suoritusajankohta"] == "8/2026–5/2027"
    assert sheets[0].rows[1].values["suoritusajankohta"] == "syksy 2026"  # Excelin alkuperäinen

    # muokkaus säilyy, kun esikatselu rakennetaan uudelleen (esim. rastin vaihto)
    win.contact_check.setChecked(False)
    win.update_preview()
    assert win.preview.item(0, col).text() == "8/2026–5/2027"  # type: ignore[union-attr]


def test_fill_mode_radios_default_hint_and_persistence(qtbot, config_path: Path) -> None:
    from opiskelusuunnitelmoittaja.fillmode import FillMode

    win = MainWindow(config_path)
    qtbot.addWidget(win)
    assert [rb.text() for rb in win.mode_buttons.values()] == [
        "Lisää loppuun",
        "Korvaa olemassa oleva opintosuunnitelma",
        "Täydennä puuttuvat",
    ]
    assert win.selected_fill_mode() is FillMode.APPEND  # config.jsonin oletus
    assert win.mode_hint.text() == FillMode.APPEND.description

    win.mode_buttons[FillMode.COMPLETE].setChecked(True)
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
