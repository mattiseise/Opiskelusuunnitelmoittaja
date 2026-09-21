"""Pääikkuna: opiskelijan valinnat, Excel-esikatselu, Chromen tila, täyttö ja loki."""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, Slot
from PySide6.QtGui import QAction, QCloseEvent, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
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
    QScrollArea,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import APP_TITLE, __version__
from ..browser import BrowserError, is_chrome_listening, launch_chrome
from ..config import Config, ConfigError, load_config
from ..contact import QUESTION as CONTACT_QUESTION
from ..excel import ExcelError, PlanRow, Sheet, list_sheets, read_sheet
from ..filler import Summary
from ..logsetup import setup_logging
from . import theme
from .preview_table import GRIP, GripDelegate, PreviewTable
from .settings_dialog import SettingsDialog
from .worker import FillWorker, QtLogHandler, ReadWorker

log = logging.getLogger("suunnitelmoittaja.gui")
TIME_FIELD = "suoritusajankohta"
WILMA_SHEET = "Wilma"
GRIP_COL = 0  # tarttuma raahaukseen
CHECK_COL = 1
SOURCE_COL = 2
FIELD_COLUMN_OFFSET = 3  # 3… = kentät


@dataclass
class PreviewRow:
    """Yksi esikatselun rivi. key = (lähde, järjestysnumero lähteessä), pysyy muokkauksissa."""

    sheet: str
    key: tuple[str, int]
    values: dict[str, str]
    checked: bool = True


LEVEL_COLORS = {"WARNING": "#9C7A3A", "ERROR": "#69013B", "CRITICAL": "#4A0029"}


class MainWindow(QMainWindow):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self.config: Config = Config()
        self.settings = QSettings("Seise", "OpintosuunnitelmanTayttaja")
        self.worker: FillWorker | None = None
        self._available_sheets: list[str] = []
        self._preview_sheets: list[Sheet] = []
        self._preview_rows: list[PreviewRow] = []
        self._edits: dict[tuple[str, int], dict[str, str]] = {}  # key → muokatut kentät
        self._unchecked: set[tuple[str, int]] = set()
        self._order: list[tuple[str, int]] = []  # käyttäjän järjestys, jos riviä siirretty
        self._wilma_rows: list[PlanRow] = []
        self.reader: ReadWorker | None = None

        self.setWindowTitle(APP_TITLE)
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
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- otsikkovyö (burgundi section)
        header = QWidget()
        header.setProperty("role", "section")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        h = QHBoxLayout(header)
        h.setContentsMargins(40, 22, 40, 22)
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        eyebrow = _label("BUSINESS COLLEGE HELSINKI · OPISKELUSUUNNITELMAT", "eyebrow")
        title = _label(APP_TITLE, "title")
        title_box.addWidget(eyebrow)
        title_box.addWidget(title)
        h.addLayout(title_box, 1)
        meta = QVBoxLayout()
        meta.setSpacing(2)
        version = QLabel(f"Versio {__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignRight)
        version.setStyleSheet(f"color: {theme.TOKENS['muted_on_dark']}; font-size: 12px;")
        btn_settings = QPushButton("Asetukset")
        btn_settings.setProperty("variant", "link")
        btn_settings.setStyleSheet(
            f"color: {theme.TOKENS['on_section']}; text-decoration: underline; font-size: 13px;"
        )
        btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_settings.clicked.connect(self.open_settings)
        meta.addWidget(version)
        meta.addWidget(btn_settings, 0, Qt.AlignmentFlag.AlignRight)
        h.addLayout(meta)
        outer.addWidget(header)

        # --- runko: vasen sarake (1 Chrome, 2 Opiskelija) | oikea sarake (3 Esikatselu, 4 Täyttö)
        body = QHBoxLayout()
        body.setContentsMargins(40, 28, 40, 16)
        body.setSpacing(0)
        outer.addLayout(body, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 24, 0)
        left_layout.setSpacing(0)
        left_scroll = QScrollArea()
        left_scroll.setWidget(left)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setFixedWidth(420)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet(
            "QScrollArea { background: transparent; } "
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        body.addWidget(left_scroll)

        vline = QFrame()
        vline.setProperty("role", "vhairline")
        vline.setFrameShape(QFrame.Shape.NoFrame)
        body.addWidget(vline)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(32, 0, 0, 0)
        right_layout.setSpacing(0)
        body.addWidget(right, 1)

        # 1 · Chrome
        left_layout.addLayout(self._step_header("1", "Käynnistä Chrome"))
        self.chrome_label = _label("Tarkistetaan yhteyttä…", "status-off")
        self.chrome_label.setWordWrap(True)
        left_layout.addWidget(self.chrome_label)
        chrome_row = QHBoxLayout()
        chrome_row.setContentsMargins(0, 10, 0, 0)
        self.btn_chrome = QPushButton("Käynnistä Chrome")
        self.btn_chrome.clicked.connect(self.start_chrome)
        chrome_row.addWidget(self.btn_chrome)
        chrome_row.addStretch()
        left_layout.addLayout(chrome_row)
        self.chrome_hint = _label("", "muted")
        self.chrome_hint.setWordWrap(True)
        self.chrome_hint.setContentsMargins(0, 10, 0, 0)
        left_layout.addWidget(self.chrome_hint)
        left_layout.addWidget(_hairline(top=16, bottom=16))

        # 2 · Avaa opiskelijan opintokortti
        left_layout.addLayout(self._step_header("2", "Avaa opiskelijan opintokortti"))
        self.form_hint = _label(
            "Siirry Chrome-ikkunassa Wilmaan, avaa opiskelijan opintokortti ja siitä "
            "Opintosuunnitelma-lomake muokkaustilassa. Jätä välilehti auki: työkalu täyttää "
            "sen taulukon.",
            "muted",
        )
        self.form_hint.setWordWrap(True)
        left_layout.addWidget(self.form_hint)
        left_layout.addWidget(_hairline(top=16, bottom=16))

        # 3 · Valitse opinnot
        step3 = self._step_header("3", "Valitse opinnot")
        btn_excel_help = QPushButton("Ohje Excelistä")
        btn_excel_help.setProperty("variant", "link")
        btn_excel_help.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_excel_help.clicked.connect(self.show_excel_help)
        step3.addWidget(btn_excel_help)
        left_layout.addLayout(step3)
        excel_caps = QHBoxLayout()
        excel_caps.setSpacing(6)
        excel_caps.addWidget(_label("LÄHDE-EXCEL", "caps"))
        excel_caps.addStretch()
        btn_browse = QPushButton("Vaihda")
        btn_browse.setProperty("variant", "link")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.clicked.connect(self.choose_excel)
        btn_reload = QPushButton("Lataa uudelleen")
        btn_reload.setProperty("variant", "link")
        btn_reload.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reload.clicked.connect(self.reload_excel)
        excel_caps.addWidget(btn_browse)
        excel_caps.addWidget(_label("·", "muted"))
        excel_caps.addWidget(btn_reload)
        left_layout.addLayout(excel_caps)
        self.excel_edit = QLineEdit()
        self.excel_edit.setReadOnly(True)
        self.excel_edit.setFrame(False)
        self.excel_edit.setStyleSheet(
            "background: transparent; border: none; "
            f"border-bottom: 1px solid {theme.TOKENS['hairline_strong']}; "
            f"padding: 2px 0 6px 0; color: {theme.TOKENS['ink_soft']}; font-size: 13px;"
        )
        left_layout.addWidget(self.excel_edit)
        self.excel_hint = _label(
            "Yksi välilehti = yksi suunnitelma. Otsikkorivillä Osaamistavoite, Laajuus, "
            "Suoritustapa / osaaminen hankitaan ja Suoritusajankohta.",
            "muted",
        )
        self.excel_hint.setWordWrap(True)
        self.excel_hint.setContentsMargins(0, 6, 0, 0)
        left_layout.addWidget(self.excel_hint)

        self.group_main = QGroupBox()
        self.group_main.setFlat(True)
        gm = QVBoxLayout(self.group_main)
        gm.setContentsMargins(0, 12, 0, 0)
        gm.setSpacing(2)
        self.main_caps = _label("PÄÄSUUNTAUS", "caps")
        gm.addWidget(self.main_caps)
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(0)
        gm.addLayout(self.main_layout)
        self.main_group = QButtonGroup(self)
        self.main_group.setExclusive(True)
        left_layout.addWidget(self.group_main)

        self.group_optional = QGroupBox()
        self.group_optional.setFlat(True)
        go = QVBoxLayout(self.group_optional)
        go.setContentsMargins(0, 10, 0, 0)
        go.setSpacing(2)
        go.addWidget(_label("LISÄKSI", "caps"))
        self.optional_layout = QVBoxLayout()
        self.optional_layout.setSpacing(0)
        go.addLayout(self.optional_layout)
        left_layout.addWidget(self.group_optional)

        left_layout.addWidget(_hairline(top=12, bottom=4))
        self.manual_toggle = QCheckBox("Valitse välilehdet käsin")
        self.manual_toggle.toggled.connect(self._toggle_manual)
        left_layout.addWidget(self.manual_toggle)
        self.manual_list = QListWidget()
        self.manual_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.manual_list.itemChanged.connect(lambda _item: self.update_preview())
        self.manual_list.setVisible(False)
        self.manual_list.setMaximumHeight(190)
        left_layout.addWidget(self.manual_list)
        self.separator_check = QCheckBox("Tyhjä välirivi välilehtien väliin")
        self.separator_check.toggled.connect(lambda _c: self.update_preview())
        left_layout.addWidget(self.separator_check)
        self.contact_check = QCheckBox(CONTACT_QUESTION.rstrip("?"))
        self.contact_check.toggled.connect(lambda _c: self.update_preview())
        left_layout.addWidget(self.contact_check)
        self.contact_hint = _label("", "muted")
        self.contact_hint.setWordWrap(True)
        left_layout.addWidget(self.contact_hint)
        left_layout.addStretch()

        # 4 · Esikatselu ja muokkaus
        step4 = self._step_header("4", "Esikatselu ja muokkaus")
        self.btn_read_wilma = QPushButton("Hae nykyiset rivit Wilmasta")
        self.btn_read_wilma.setProperty("variant", "link")
        self.btn_read_wilma.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_read_wilma.setToolTip(
            "Lukee avoimen opintosuunnitelmalomakkeen rivit esikatseluun, jossa niitä voi "
            "muokata, järjestää ja yhdistää Excelin riveihin."
        )
        self.btn_read_wilma.clicked.connect(self.read_from_wilma)
        step4.addWidget(self.btn_read_wilma)
        step4.addWidget(_label("·", "muted"))
        self.btn_set_time = QPushButton("Aseta ajankohta valituille")
        self.btn_set_time.setProperty("variant", "link")
        self.btn_set_time.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_set_time.setToolTip(
            "Kirjoittaa saman suoritusajankohdan kaikille rastitetuille riveille. "
            "Solua voi muokata myös kaksoisnapsauttamalla."
        )
        self.btn_set_time.clicked.connect(self.set_time_for_checked)
        step4.addWidget(self.btn_set_time)
        step4.addWidget(_label("·", "muted"))
        self.btn_up = QPushButton("▲")
        self.btn_up.setProperty("variant", "link")
        self.btn_up.setToolTip("Siirrä valittu rivi ylös")
        self.btn_up.clicked.connect(lambda: self.move_current_row(-1))
        self.btn_down = QPushButton("▼")
        self.btn_down.setProperty("variant", "link")
        self.btn_down.setToolTip("Siirrä valittu rivi alas")
        self.btn_down.clicked.connect(lambda: self.move_current_row(1))
        step4.addWidget(self.btn_up)
        step4.addWidget(self.btn_down)
        step4.addStretch()
        self.preview_label = _label("", "caps")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        step4.addWidget(self.preview_label)
        right_layout.addLayout(step4)
        self.preview = PreviewTable(0, 7)
        self.preview.setHorizontalHeaderLabels(
            ["", "", "Lähde", "Osaamistavoite", "Laajuus", "Suoritustapa", "Ajankohta"]
        )
        self.preview.row_moved.connect(self.move_row)
        hh = self.preview.horizontalHeader()
        hh.setSectionResizeMode(GRIP_COL, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(GRIP_COL, 28)
        self.preview.setItemDelegateForColumn(
            GRIP_COL, GripDelegate(theme.TOKENS["gold"], self.preview)
        )
        hh.setSectionResizeMode(CHECK_COL, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(CHECK_COL, 36)
        hh.setSectionResizeMode(SOURCE_COL, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hh.setMinimumSectionSize(28)
        self.preview.itemChanged.connect(self._on_preview_item_changed)
        # "Valitse kaikki / poista valinnat" -rasti otsikkorivin tyhjässä solussa
        self.header_check = QCheckBox(hh)
        self.header_check.setTristate(True)
        self.header_check.setToolTip("Valitse kaikki / poista valinnat")
        self.header_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_check.setStyleSheet("QCheckBox { padding: 0; margin: 0; spacing: 0; }")
        self.header_check.clicked.connect(self.toggle_all_rows)
        hh.sectionResized.connect(lambda *_a: self._place_header_check())
        hh.geometriesChanged.connect(self._place_header_check)
        self._place_header_check()
        hh.setHighlightSections(False)
        self.preview.setFont(theme.sans(13))
        # Kaikki kenttäsolut ovat muokattavia; rasti- ja lähdesolut eivät
        self.preview.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.preview.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview.setShowGrid(False)
        self.preview.setAlternatingRowColors(True)
        self.preview.verticalHeader().setVisible(False)
        self.preview.verticalHeader().setDefaultSectionSize(34)
        self.preview.setWordWrap(False)
        right_layout.addWidget(self.preview, 3)

        right_layout.addWidget(_hairline(top=22, bottom=22))

        # 5 · Täyttö
        right_layout.addLayout(self._step_header("5", "Täyttö"))
        mode_row = QHBoxLayout()
        mode_row.setSpacing(18)
        self.mode_append = QRadioButton("Lisää lomakkeen loppuun")
        self.mode_replace = QRadioButton("Korvaa lomakkeen nykyiset rivit")
        self.mode_append.setChecked(True)
        self.mode_replace.setToolTip(
            "Poistaa lomakkeen kaikki rivit ja kirjoittaa esikatselun rivit tilalle. "
            "Käytä tätä, kun olet hakenut rivit Wilmasta ja muokannut niitä."
        )
        mode_row.addWidget(self.mode_append)
        mode_row.addWidget(self.mode_replace)
        mode_row.addStretch()
        right_layout.addLayout(mode_row)
        right_layout.addSpacing(8)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.btn_fill = QPushButton("Täytä lomake")
        self.btn_fill.setProperty("variant", "primary")
        self.btn_fill.setDefault(True)
        self.btn_fill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fill.clicked.connect(self.start_fill)
        actions.addWidget(self.btn_fill)
        self.btn_stop = QPushButton("Keskeytä")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_fill)
        actions.addWidget(self.btn_stop)
        actions.addSpacing(12)
        self.progress_label = _label("", "muted")
        actions.addWidget(self.progress_label, 1)
        right_layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        right_layout.addSpacing(14)
        right_layout.addWidget(self.progress)
        right_layout.addSpacing(12)
        self.log_view = QPlainTextEdit()
        self.log_view.setProperty("role", "log")
        self.log_view.setReadOnly(True)
        self.log_view.setFrameShape(QFrame.Shape.NoFrame)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setMinimumHeight(110)
        self.log_view.setPlaceholderText("Täytön loki näkyy tässä.")
        right_layout.addWidget(self.log_view, 2)

        self.statusBar().showMessage("Valmis")

    def _step_header(self, number: str, title: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.setContentsMargins(0, 0, 0, 12)
        num = _label(number, "step-number")
        num.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        ttl = _label(title, "step-title")
        ttl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        row.addWidget(num)
        row.addWidget(ttl)
        row.addStretch()
        return row

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
        self.excel_edit.setText(_short_path(self.excel_path))
        self.excel_edit.setToolTip(str(self.excel_path))
        self.separator_check.setChecked(self.config.separator_row_between_sheets)
        teacher = self.config.teacher
        self.contact_check.blockSignals(True)
        self.contact_check.setEnabled(teacher.is_configured())
        self.contact_check.setChecked(teacher.is_configured() and teacher.default)
        self.contact_check.blockSignals(False)
        self.contact_hint.setText(
            f"{teacher.name}{theme.MIDDOT}{teacher.email}{theme.MIDDOT}{teacher.phone}".strip(" ·")
            if teacher.is_configured()
            else "Lisää opettajan nimi, sähköposti ja puhelin Asetukset → Opettaja."
        )
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
            self.main_caps.setText(wizard.main_question.upper().rstrip("?"))
            for name in mains:
                rb = QRadioButton(name)
                rb.toggled.connect(lambda _c: self.update_preview())
                self.main_group.addButton(rb)
                self.main_layout.addWidget(rb)
            self.main_group.buttons()[0].setChecked(True)
            for opt in wizard.optional_sheets:
                if opt.sheet not in self._available_sheets:
                    continue
                cb = QCheckBox(f"{opt.question.rstrip('?')}{theme.MIDDOT}{opt.sheet}")
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
        """Rakenna esikatselu: Wilman rivit, valitut Excel-välilehdet, yhteystietorivi.

        Käyttäjän muokkaukset (_edits), rastien poistot (_unchecked) ja rivijärjestys
        (_order) säilyvät avaimen (lähde, järjestysnumero) perusteella.
        """
        names = self.selected_sheet_names()
        rows: list[PreviewRow] = []
        for i, wr in enumerate(self._wilma_rows):
            rows.append(PreviewRow(WILMA_SHEET, (WILMA_SHEET, i), dict(wr.values)))
        for name in names:
            try:
                sheet = read_sheet(self.excel_path, name, self.config.excel_columns)
            except ExcelError as exc:
                log.error(str(exc))
                continue
            for i, r in enumerate(sheet.rows):
                rows.append(PreviewRow(sheet.name, (sheet.name, i), dict(r.values)))
        if self.contact_check.isChecked():
            contact_sheet = self.config.teacher.sheet(self.config.field_names)
            if contact_sheet is not None:
                rows.append(
                    PreviewRow(
                        contact_sheet.name,
                        (contact_sheet.name, 0),
                        dict(contact_sheet.rows[0].values),
                    )
                )
                names = [*names, contact_sheet.name]
        if self._wilma_rows:
            names = [WILMA_SHEET, *names]

        for row in rows:
            row.values.update(self._edits.get(row.key, {}))
            row.checked = row.key not in self._unchecked
        if self._order:
            pos = {k: i for i, k in enumerate(self._order)}
            rows.sort(key=lambda r: pos.get(r.key, len(pos)))
        self._preview_rows = rows
        self._render_preview()
        self._refresh_preview_summary(names)

    def _render_preview(self) -> None:
        fields = self.config.field_names
        self.preview.blockSignals(True)
        self.preview.setRowCount(0)
        for row in self._preview_rows:
            r = self.preview.rowCount()
            self.preview.insertRow(r)
            grip = QTableWidgetItem(GRIP)
            grip.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            grip.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            grip.setForeground(QColor(theme.TOKENS["gold"]))
            grip.setToolTip("Raahaa riviä uuteen paikkaan")
            self.preview.setItem(r, GRIP_COL, grip)
            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            check.setCheckState(Qt.CheckState.Checked if row.checked else Qt.CheckState.Unchecked)
            self.preview.setItem(r, CHECK_COL, check)
            src = QTableWidgetItem(row.sheet)
            src.setFlags(
                (src.flags() & ~Qt.ItemFlag.ItemIsEditable) | Qt.ItemFlag.ItemIsDragEnabled
            )
            self.preview.setItem(r, SOURCE_COL, src)
            for col, field in enumerate(fields[:4], start=FIELD_COLUMN_OFFSET):
                item = QTableWidgetItem(row.values.get(field, ""))
                item.setFlags(
                    item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsDragEnabled
                )
                item.setToolTip("Kaksoisnapsauta muokataksesi")
                self.preview.setItem(r, col, item)
        self.preview.blockSignals(False)

    def checked_row_indices(self) -> list[int]:
        return [
            r
            for r in range(self.preview.rowCount())
            if (item := self.preview.item(r, CHECK_COL)) is not None
            and item.checkState() == Qt.CheckState.Checked
        ]

    def selected_sheets_for_fill(self) -> list[Sheet]:
        """Rastitut rivit taulukon järjestyksessä; peräkkäiset saman lähteen rivit yhdeksi
        välilehdeksi, jotta välirivit tulevat lähteiden rajoille."""
        checked = set(self.checked_row_indices())
        result: list[Sheet] = []
        for idx, row in enumerate(self._preview_rows):
            if idx not in checked:
                continue
            plan = PlanRow({f: row.values.get(f, "") for f in self.config.field_names})
            if result and result[-1].name == row.sheet:
                result[-1].rows.append(plan)
            else:
                result.append(Sheet(row.sheet, [plan]))
        return result

    def _time_column(self) -> int | None:
        fields = self.config.field_names[:4]
        return FIELD_COLUMN_OFFSET + fields.index(TIME_FIELD) if TIME_FIELD in fields else None

    def _field_for_column(self, col: int) -> str | None:
        fields = self.config.field_names[:4]
        i = col - FIELD_COLUMN_OFFSET
        return fields[i] if 0 <= i < len(fields) else None

    def set_time_for_checked(self) -> None:
        time_col = self._time_column()
        if time_col is None:
            return
        checked = self.checked_row_indices()
        if not checked:
            return
        current = self.preview.item(checked[0], time_col)
        text, ok = QInputDialog.getText(
            self,
            "Suoritusajankohta",
            f"Ajankohta {len(checked)} valitulle riville (esim. 8/2026–5/2027):",
            text=current.text() if current is not None else "",
        )
        if not ok:
            return
        self.preview.blockSignals(True)
        for r in checked:
            item = self.preview.item(r, time_col)
            if item is not None:
                item.setText(text.strip())
            self._record_edit(r, TIME_FIELD, text.strip())
        self.preview.blockSignals(False)

    def _record_edit(self, r: int, field: str, value: str) -> None:
        row = self._preview_rows[r]
        row.values[field] = value
        self._edits.setdefault(row.key, {})[field] = value

    def move_current_row(self, delta: int) -> None:
        r = self.preview.currentRow()
        self.move_row(r, r + delta)

    def move_row(self, src: int, dst: int) -> None:
        """Siirrä rivi paikasta src paikkaan dst (raahaus tai ▲▼)."""
        rows = self._preview_rows
        if src < 0 or not 0 <= dst < len(rows) or src == dst:
            return
        row = rows.pop(src)
        rows.insert(dst, row)
        self._order = [r.key for r in rows]
        self._render_preview()
        self.preview.selectRow(dst)
        self._refresh_preview_summary(self.selected_sheet_names())

    def read_from_wilma(self) -> None:
        """Lue avoimen lomakkeen rivit esikatseluun (Wilma-lähde)."""
        if self.reader is not None:
            return
        if not is_chrome_listening(self.config.browser):
            QMessageBox.warning(
                self, "Chrome ei ole käynnissä", "Käynnistä Chrome ja avaa opintokortti ensin."
            )
            return
        self.btn_read_wilma.setEnabled(False)
        self.statusBar().showMessage("Luetaan lomakkeen rivejä…")
        self.reader = ReadWorker(self.config)
        self.reader.finished_ok.connect(self._on_wilma_rows)
        self.reader.failed.connect(self._on_wilma_failed)
        self.reader.finished.connect(self._on_reader_done)
        self.reader.start()

    @Slot(object)
    def _on_wilma_rows(self, rows: list[PlanRow]) -> None:
        self._wilma_rows = list(rows)
        # vanhat Wilma-muokkaukset eivät enää vastaa uutta lukua
        for key in [k for k in self._edits if k[0] == WILMA_SHEET]:
            del self._edits[key]
        self._unchecked = {k for k in self._unchecked if k[0] != WILMA_SHEET}
        self._order = []
        self.update_preview()
        if rows:
            self.mode_replace.setChecked(True)
            self.statusBar().showMessage(
                f"Luettiin {len(rows)} riviä Wilmasta. Täyttötila: korvaa nykyiset rivit.", 6000
            )
        else:
            self.statusBar().showMessage("Lomakkeella ei ole rivejä.", 4000)

    @Slot(str)
    def _on_wilma_failed(self, message: str) -> None:
        log.error(message)
        QMessageBox.critical(self, "Luku epäonnistui", message)

    def _on_reader_done(self) -> None:
        self.reader = None
        self.btn_read_wilma.setEnabled(True)

    def clear_wilma_rows(self) -> None:
        self._wilma_rows = []
        self._order = []
        self.update_preview()

    def toggle_all_rows(self, *_args: object) -> None:
        """Otsikkorivin rasti: kaikki valittuna → poista valinnat, muuten → valitse kaikki."""
        all_checked = len(self.checked_row_indices()) == self.preview.rowCount()
        state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        self.preview.blockSignals(True)
        for r in range(self.preview.rowCount()):
            item = self.preview.item(r, CHECK_COL)
            if item is not None:
                item.setCheckState(state)
            row = self._preview_rows[r]
            row.checked = state == Qt.CheckState.Checked
            if row.checked:
                self._unchecked.discard(row.key)
            else:
                self._unchecked.add(row.key)
        self.preview.blockSignals(False)
        self._refresh_preview_summary(self.selected_sheet_names())

    def _on_preview_item_changed(self, item: QTableWidgetItem) -> None:
        r = item.row()
        if not 0 <= r < len(self._preview_rows):
            return
        if item.column() == CHECK_COL:
            row = self._preview_rows[r]
            row.checked = item.checkState() == Qt.CheckState.Checked
            if row.checked:
                self._unchecked.discard(row.key)
            else:
                self._unchecked.add(row.key)
            self._refresh_preview_summary(self.selected_sheet_names())
            return
        field = self._field_for_column(item.column())
        if field is not None:
            self._record_edit(r, field, item.text().strip())

    def _refresh_preview_summary(self, names: list[str]) -> None:
        total = self.preview.rowCount()
        checked = len(self.checked_row_indices())
        count = f"{checked} / {total} RIVIÄ" if checked != total else f"{total} RIVIÄ"
        self.preview_label.setText(
            count + (f"{theme.MIDDOT}{', '.join(names).upper()}" if names else "")
        )
        self.header_check.blockSignals(True)
        if total == 0 or checked == 0:
            self.header_check.setCheckState(Qt.CheckState.Unchecked)
        elif checked == total:
            self.header_check.setCheckState(Qt.CheckState.Checked)
        else:
            self.header_check.setCheckState(Qt.CheckState.PartiallyChecked)
        self.header_check.blockSignals(False)
        self.header_check.setEnabled(total > 0)
        self.btn_fill.setEnabled(checked > 0 and self.worker is None)

    def _place_header_check(self) -> None:
        hh = self.preview.horizontalHeader()
        w = hh.sectionSize(CHECK_COL)
        h = hh.height()
        size = self.header_check.sizeHint()
        self.header_check.move(
            hh.sectionViewportPosition(CHECK_COL) + max(0, (w - size.width()) // 2),
            max(0, (h - size.height()) // 2),
        )
        self.header_check.raise_()

    # ------------------------------------------------------------------ toiminnot

    def choose_excel(self) -> None:
        start = str(self.excel_path.parent if self.excel_path.exists() else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Valitse Excel-tiedosto", start, "Excel (*.xlsx *.xlsm);;Kaikki (*)"
        )
        if path:
            self.excel_path = Path(path)
            self.excel_edit.setText(_short_path(self.excel_path))
            self.excel_edit.setToolTip(path)
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
            _set_role(self.chrome_label, "status-ok")
            self.chrome_label.setText(f"Yhteys kunnossa{theme.MIDDOT}portti {port}")
            self.btn_chrome.setText("Chrome on käynnissä")
            self.btn_chrome.setEnabled(False)
            self.chrome_hint.setText("Chrome on auki. Jatka kohtaan 2.")
        else:
            _set_role(self.chrome_label, "status-off")
            self.chrome_label.setText(f"Ei yhteyttä{theme.MIDDOT}portti {port}")
            self.btn_chrome.setText("Käynnistä Chrome")
            self.btn_chrome.setEnabled(True)
            self.chrome_hint.setText(
                "Chrome avataan erilliseen profiiliin, johon Wilma-kirjautuminen säilyy "
                "kertojen välillä."
            )

    def start_fill(self) -> None:
        if self.worker is not None:
            return
        sheets = self.selected_sheets_for_fill()
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
        replace_existing = self.mode_replace.isChecked()
        mode_text = (
            "Lomakkeen nykyiset rivit KORVATAAN esikatselun riveillä (tallennetut rivit "
            "kirjoitetaan yli paikallaan, ylijäävät jäävät tyhjiksi)."
            if replace_existing
            else "Rivit lisätään lomakkeen loppuun."
        )
        answer = QMessageBox.question(
            self,
            "Täytetäänkö lomake?",
            f"Täytetään {total} riviä lähteistä:\n{', '.join(s.name for s in sheets)}\n\n"
            f"{mode_text}\nVarmista, että opintokortin lomake on auki Chromessa.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        config = replace(self.config, separator_row_between_sheets=self.separator_check.isChecked())
        self.log_view.clear()
        self.progress.setMaximum(total)
        self.progress.setValue(0)
        self.progress_label.setText(f"0 / {total} riviä")
        self.worker = FillWorker(config, sheets, replace_existing=replace_existing)
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
        self.btn_fill.setEnabled(not running and bool(self.checked_row_indices()))
        self.btn_stop.setEnabled(running)
        self.group_main.setEnabled(not running and not self.manual_toggle.isChecked())
        self.group_optional.setEnabled(not running and not self.manual_toggle.isChecked())
        self.manual_list.setEnabled(not running)
        self.statusBar().showMessage("Täytetään…" if running else "Valmis")

    @Slot(int, int, str)
    def _on_progress(self, done: int, total: int, message: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.progress_label.setText(
            f"{done} / {total} riviä" + (f"{theme.MIDDOT}{message}" if message else "")
        )

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

    def show_excel_help(self) -> None:
        QMessageBox.information(
            self,
            "Lähde-Excel",
            "<b>Miten Excel rakennetaan</b><br><br>"
            "Jokainen välilehti on yksi suunnitelma tai suunnitelman osa (esim. "
            "Ohjelmistokehittäjä, Kyber, Lukio, YTO). Ensimmäinen rivi on otsikkorivi, ja "
            "siltä pitää löytyä otsikot <i>Osaamistavoite</i>, <i>Laajuus</i>, "
            "<i>Suoritustapa / osaaminen hankitaan</i> ja <i>Suoritusajankohta</i> "
            "(kirjainkoko ei haittaa). Jokainen seuraava rivi on yksi lomakkeen rivi.<br><br>"
            "Kokonaan tyhjät rivit ohitetaan. Numerot muotoillaan siististi (25.0 → 25). "
            "Tyhjä solu täytetään lomakkeelle välilyönnillä, koska Wilma ei hyväksy tyhjää "
            "kenttää.<br><br>"
            "Pääsuuntaukset ja kyllä/ei-kysymykset kytketään välilehtiin Asetukset → Kysely. "
            "Toisen Excel-tiedoston voi valita <i>Vaihda</i>-linkistä; valinta muistetaan.",
        )

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
            APP_TITLE,
            f"<b>{APP_TITLE} {__version__}</b><br>"
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


def _short_path(path: Path) -> str:
    """Kansio · tiedosto, jotta pitkä polku ei katkea alusta."""
    return f"{path.parent.name}{theme.MIDDOT}{path.name}" if path.parent.name else path.name


def _label(text: str, role: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", role)
    return lbl


def _set_role(widget: QWidget, role: str) -> None:
    widget.setProperty("role", role)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def _hairline(*, top: int = 0, bottom: int = 0) -> QWidget:
    """Hairline-viiva pystyvälistyksellä."""
    holder = QWidget()
    lay = QVBoxLayout(holder)
    lay.setContentsMargins(0, top, 0, bottom)
    line = QFrame()
    line.setProperty("role", "hairline")
    line.setFrameShape(QFrame.Shape.NoFrame)
    lay.addWidget(line)
    return holder


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
