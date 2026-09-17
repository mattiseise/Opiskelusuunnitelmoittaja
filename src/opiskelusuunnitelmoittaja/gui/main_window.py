"""Pääikkuna: opiskelijan valinnat, Excel-esikatselu, Chromen tila, täyttö ja loki."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, Slot
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..browser import BrowserError, is_chrome_listening, launch_chrome
from ..config import Config, ConfigError, load_config
from ..excel import ExcelError, Sheet, list_sheets, read_sheet
from ..filler import Summary
from ..logsetup import setup_logging
from .settings_dialog import SettingsDialog
from .worker import FillWorker, QtLogHandler

log = logging.getLogger("suunnitelmoittaja.gui")

LEVEL_COLORS = {"WARNING": "#b26a00", "ERROR": "#b00020", "CRITICAL": "#b00020"}


class MainWindow(QMainWindow):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self.config: Config = Config()
        self.settings = QSettings("Seise", "Opiskelusuunnitelmoittaja")
        self.worker: FillWorker | None = None
        self._available_sheets: list[str] = []
        self._preview_sheets: list[Sheet] = []

        self.setWindowTitle(f"Opiskelusuunnitelmoittaja {__version__}")
        self.resize(1080, 760)

        self._build_menu()
        self._build_ui()
        self._install_log_handler()
        self.reload_config()

        self._chrome_timer = QTimer(self)
        self._chrome_timer.timeout.connect(self._poll_chrome)
        self._chrome_timer.start(2000)
        self._poll_chrome()

    # ------------------------------------------------------------------ rakenne

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("Tiedosto")
        act_settings = QAction("Asetukset…", self)
        act_settings.setShortcut("Ctrl+,")
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)
        act_log = QAction("Avaa lokitiedosto", self)
        act_log.triggered.connect(self.open_log_file)
        menu.addAction(act_log)
        act_folder = QAction("Avaa asetuskansio", self)
        act_folder.triggered.connect(lambda: self._open_path(self.config_path.parent))
        menu.addAction(act_folder)
        menu.addSeparator()
        act_quit = QAction("Lopeta", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        menu.addAction(act_quit)

        help_menu = self.menuBar().addMenu("Ohje")
        act_about = QAction("Tietoja", self)
        act_about.triggered.connect(self.show_about)
        help_menu.addAction(act_about)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        # --- ylärivi: Excel + Chrome
        top = QHBoxLayout()
        top.addWidget(QLabel("Excel:"))
        self.excel_edit = QLineEdit()
        self.excel_edit.setReadOnly(True)
        top.addWidget(self.excel_edit, 1)
        btn_browse = QPushButton("Selaa…")
        btn_browse.clicked.connect(self.choose_excel)
        top.addWidget(btn_browse)
        btn_reload = QPushButton("Lataa uudelleen")
        btn_reload.clicked.connect(self.reload_excel)
        top.addWidget(btn_reload)
        outer.addLayout(top)

        chrome_row = QHBoxLayout()
        self.chrome_dot = QLabel("●")
        self.chrome_dot.setStyleSheet("color: #999; font-size: 18px;")
        chrome_row.addWidget(self.chrome_dot)
        self.chrome_label = QLabel("Chrome: tarkistetaan…")
        chrome_row.addWidget(self.chrome_label, 1)
        self.btn_chrome = QPushButton("Käynnistä Chrome")
        self.btn_chrome.clicked.connect(self.start_chrome)
        chrome_row.addWidget(self.btn_chrome)
        btn_settings = QPushButton("Asetukset…")
        btn_settings.clicked.connect(self.open_settings)
        chrome_row.addWidget(btn_settings)
        outer.addLayout(chrome_row)

        # --- keskiosa: valinnat | esikatselu
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.group_main = QGroupBox("Pääsuuntaus")
        self.main_layout = QVBoxLayout(self.group_main)
        self.main_group = QButtonGroup(self)
        self.main_group.setExclusive(True)
        left_layout.addWidget(self.group_main)

        self.group_optional = QGroupBox("Lisäksi")
        self.optional_layout = QVBoxLayout(self.group_optional)
        left_layout.addWidget(self.group_optional)

        self.manual_toggle = QCheckBox("Valitse välilehdet käsin")
        self.manual_toggle.toggled.connect(self._toggle_manual)
        left_layout.addWidget(self.manual_toggle)
        self.manual_list = QListWidget()
        self.manual_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.manual_list.itemChanged.connect(lambda _item: self.update_preview())
        self.manual_list.setVisible(False)
        left_layout.addWidget(self.manual_list, 1)

        self.separator_check = QCheckBox("Tyhjä välirivi välilehtien väliin")
        self.separator_check.toggled.connect(lambda _c: self.update_preview())
        left_layout.addWidget(self.separator_check)
        left_layout.addStretch()
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_label = QLabel("Esikatselu")
        right_layout.addWidget(self.preview_label)
        self.preview = QTableWidget(0, 5)
        self.preview.setHorizontalHeaderLabels(
            ["Välilehti", "Osaamistavoite", "Laajuus", "Suoritustapa", "Ajankohta"]
        )
        self.preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.preview.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview.verticalHeader().setVisible(False)
        right_layout.addWidget(self.preview, 1)
        splitter.addWidget(right)
        splitter.setSizes([340, 740])

        # --- alaosa: toiminnot, eteneminen, loki
        actions = QHBoxLayout()
        self.btn_fill = QPushButton("Täytä lomake")
        self.btn_fill.setDefault(True)
        self.btn_fill.setMinimumHeight(36)
        self.btn_fill.clicked.connect(self.start_fill)
        actions.addWidget(self.btn_fill)
        self.btn_stop = QPushButton("Keskeytä")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_fill)
        actions.addWidget(self.btn_stop)
        actions.addStretch()
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v / %m riviä")
        actions.addWidget(self.progress, 1)
        outer.addLayout(actions)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(line)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setMinimumHeight(140)
        outer.addWidget(self.log_view)

        self.statusBar().showMessage("Valmis")

    def _install_log_handler(self) -> None:
        self.log_handler = QtLogHandler()
        self.log_handler.setLevel(logging.INFO)
        self.log_handler.record.connect(self.append_log)
        logging.getLogger("suunnitelmoittaja").addHandler(self.log_handler)

    # ------------------------------------------------------------------ asetukset

    def reload_config(self) -> None:
        try:
            self.config = load_config(self.config_path)
        except ConfigError as exc:
            QMessageBox.critical(self, "Asetusvirhe", str(exc))
            self.config = Config()
        setup_logging(self.config.log_file, self.config.log_level)
        logging.getLogger("suunnitelmoittaja").addHandler(self.log_handler)

        last_excel = str(self.settings.value("excel_path", "", type=str) or "")
        excel = Path(last_excel) if last_excel and Path(last_excel).exists() else None
        self.excel_path: Path = excel or self.config.excel_file
        self.excel_edit.setText(str(self.excel_path))
        self.separator_check.setChecked(self.config.separator_row_between_sheets)
        self.reload_excel()

    def reload_excel(self) -> None:
        try:
            self._available_sheets = list_sheets(self.excel_path)
        except ExcelError as exc:
            self._available_sheets = []
            log.error(str(exc))
        self._rebuild_selectors()
        self.update_preview()

    def _rebuild_selectors(self) -> None:
        for layout in (self.main_layout, self.optional_layout):
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget() if item is not None else None
                if w is not None:
                    w.deleteLater()
        for b in self.main_group.buttons():
            self.main_group.removeButton(b)
        self.manual_list.blockSignals(True)
        self.manual_list.clear()

        wizard = self.config.wizard
        mains = [s for s in (wizard.main_sheets if wizard else []) if s in self._available_sheets]
        if wizard and mains:
            self.group_main.setTitle(wizard.main_question)
            for name in mains:
                rb = QRadioButton(name)
                rb.toggled.connect(lambda _c: self.update_preview())
                self.main_group.addButton(rb)
                self.main_layout.addWidget(rb)
            self.main_group.buttons()[0].setChecked(True)
            for opt in wizard.optional_sheets:
                if opt.sheet not in self._available_sheets:
                    continue
                cb = QCheckBox(f"{opt.question}  →  {opt.sheet}")
                cb.setProperty("sheet", opt.sheet)
                cb.setChecked(opt.default)
                cb.toggled.connect(lambda _c: self.update_preview())
                self.optional_layout.addWidget(cb)
            self.group_main.setVisible(True)
            self.group_optional.setVisible(True)
            self.manual_toggle.setChecked(False)
            self.manual_toggle.setEnabled(True)
        else:
            self.group_main.setVisible(False)
            self.group_optional.setVisible(False)
            self.manual_toggle.setChecked(True)
            self.manual_toggle.setEnabled(False)

        for name in self._available_sheets:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.manual_list.addItem(item)
        self.manual_list.blockSignals(False)

    def _toggle_manual(self, manual: bool) -> None:
        self.manual_list.setVisible(manual)
        self.group_main.setEnabled(not manual)
        self.group_optional.setEnabled(not manual)
        self.update_preview()

    # ------------------------------------------------------------------ valinnat

    def selected_sheet_names(self) -> list[str]:
        if self.manual_toggle.isChecked():
            return [
                self.manual_list.item(i).text()
                for i in range(self.manual_list.count())
                if self.manual_list.item(i).checkState() == Qt.CheckState.Checked
            ]
        chosen: list[str] = []
        checked = self.main_group.checkedButton()
        if checked is not None:
            chosen.append(checked.text())
        for i in range(self.optional_layout.count()):
            item = self.optional_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if isinstance(w, QCheckBox) and w.isChecked():
                chosen.append(str(w.property("sheet")))
        return chosen

    def update_preview(self) -> None:
        names = self.selected_sheet_names()
        sheets: list[Sheet] = []
        for name in names:
            try:
                sheets.append(read_sheet(self.excel_path, name, self.config.excel_columns))
            except ExcelError as exc:
                log.error(str(exc))
        self._preview_sheets = sheets
        fields = self.config.field_names

        self.preview.setRowCount(0)
        for sheet in sheets:
            for row in sheet.rows:
                r = self.preview.rowCount()
                self.preview.insertRow(r)
                self.preview.setItem(r, 0, QTableWidgetItem(sheet.name))
                for col, field in enumerate(fields[:4], start=1):
                    self.preview.setItem(r, col, QTableWidgetItem(row.values.get(field, "")))
        total = sum(len(s.rows) for s in sheets)
        self.preview_label.setText(
            f"Esikatselu – {total} riviä" + (f" ({', '.join(names)})" if names else "")
        )
        self.btn_fill.setEnabled(total > 0 and self.worker is None)

    # ------------------------------------------------------------------ toiminnot

    def choose_excel(self) -> None:
        start = str(self.excel_path.parent if self.excel_path.exists() else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Valitse Excel-tiedosto", start, "Excel (*.xlsx *.xlsm);;Kaikki (*)"
        )
        if path:
            self.excel_path = Path(path)
            self.excel_edit.setText(path)
            self.settings.setValue("excel_path", path)
            self.reload_excel()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self.config_path, self)
        if dialog.exec():
            self.reload_config()
            self.statusBar().showMessage("Asetukset tallennettu", 3000)

    def start_chrome(self) -> None:
        try:
            launch_chrome(self.config.browser)
            log.info("Chrome käynnistetty. Avaa lomakesivu Chrome-ikkunaan.")
        except BrowserError as exc:
            QMessageBox.warning(self, "Chrome", str(exc))
        self._poll_chrome()

    def _poll_chrome(self) -> None:
        ok = is_chrome_listening(self.config.browser, timeout_s=0.5)
        port = self.config.browser.remote_debugging_port
        if ok:
            self.chrome_dot.setStyleSheet("color: #2e7d32; font-size: 18px;")
            self.chrome_label.setText(f"Chrome: yhteys portissa {port}")
            self.btn_chrome.setText("Chrome käynnissä")
            self.btn_chrome.setEnabled(False)
        else:
            self.chrome_dot.setStyleSheet("color: #c62828; font-size: 18px;")
            self.chrome_label.setText(f"Chrome: ei yhteyttä (portti {port})")
            self.btn_chrome.setText("Käynnistä Chrome")
            self.btn_chrome.setEnabled(True)

    def start_fill(self) -> None:
        if self.worker is not None:
            return
        sheets = self._preview_sheets
        total = sum(len(s.rows) for s in sheets)
        if total == 0:
            return
        if not is_chrome_listening(self.config.browser):
            QMessageBox.warning(
                self,
                "Chrome ei ole käynnissä",
                "Käynnistä Chrome ensin ja avaa lomakesivu siihen ikkunaan.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Täytetäänkö lomake?",
            f"Täytetään {total} riviä välilehdiltä:\n{', '.join(s.name for s in sheets)}\n\n"
            "Varmista, että lomakesivu on auki Chromessa.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        from dataclasses import replace

        config = replace(self.config, separator_row_between_sheets=self.separator_check.isChecked())
        self.log_view.clear()
        self.progress.setMaximum(total)
        self.progress.setValue(0)
        self.worker = FillWorker(config, sheets)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_done)
        self._set_running(True)
        self.worker.start()

    def stop_fill(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()
            self.statusBar().showMessage("Keskeytetään nykyisen rivin jälkeen…")

    def _set_running(self, running: bool) -> None:
        self.btn_fill.setEnabled(not running and bool(self._preview_sheets))
        self.btn_stop.setEnabled(running)
        self.group_main.setEnabled(not running and not self.manual_toggle.isChecked())
        self.group_optional.setEnabled(not running and not self.manual_toggle.isChecked())
        self.manual_list.setEnabled(not running)
        self.statusBar().showMessage("Täytetään…" if running else "Valmis")

    @Slot(int, int, str)
    def _on_progress(self, done: int, total: int, message: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        if message:
            self.statusBar().showMessage(message)

    @Slot(object)
    def _on_finished(self, summary: Summary) -> None:
        lines = [
            f"{s.sheet_name}: {s.successful_rows}/{s.total_rows} riviä ({s.success_rate:.0f} %)"
            for s in summary.sheets
        ]
        text = "\n".join(lines) + (
            f"\n\nYhteensä {summary.successful_rows}/{summary.total_rows} riviä onnistui."
        )
        if summary.failed_rows:
            text += f"\nVirheitä {summary.total_errors}. Katso loki: {self.config.log_file}"
            QMessageBox.warning(self, "Täyttö valmis, virheitä", text)
        else:
            text += "\n\nTarkista rivit Wilmassa ja paina Tallenna tiedot."
            QMessageBox.information(self, "Täyttö valmis", text)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        log.error(message)
        QMessageBox.critical(self, "Täyttö epäonnistui", message)

    def _on_worker_done(self) -> None:
        self.worker = None
        self._set_running(False)

    @Slot(str, str)
    def append_log(self, level: str, message: str) -> None:
        color = LEVEL_COLORS.get(level)
        if color:
            self.log_view.appendHtml(
                f'<span style="color:{color}">{level}: {_escape(message)}</span>'
            )
        else:
            self.log_view.appendPlainText(message)

    def open_log_file(self) -> None:
        self._open_path(self.config.log_file)

    def _open_path(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.information(self, "Ei löydy", f"{path} ei ole vielä olemassa.")
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform.startswith("win"):
            import os

            os.startfile(str(path))  # type: ignore[attr-defined]  # vain Windows
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "Opiskelusuunnitelmoittaja",
            f"<b>Opiskelusuunnitelmoittaja {__version__}</b><br>"
            "Täyttää Wilman opiskelusuunnitelmalomakkeen Excel-taulukosta.<br><br>"
            f"Asetukset: {self.config_path}<br>"
            "Matti Seise · Business College Helsinki",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None and self.worker.isRunning():
            answer = QMessageBox.question(
                self, "Täyttö käynnissä", "Täyttö on kesken. Keskeytetäänkö ja suljetaan?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.request_stop()
            self.worker.wait(5000)
        logging.getLogger("suunnitelmoittaja").removeHandler(self.log_handler)
        event.accept()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
