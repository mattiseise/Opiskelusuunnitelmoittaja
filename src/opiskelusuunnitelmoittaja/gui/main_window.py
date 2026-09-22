"""Pääikkuna: opiskelijan valinnat, Excel-esikatselu, Chromen tila, täyttö ja loki."""

from __future__ import annotations

import logging
import os
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
from ..browser import (
    BrowserError,
    connect,
    find_form_page,
    is_chrome_listening,
    launch_chrome,
    student_name,
)
from ..config import Config, ConfigError, load_config
from ..contact import QUESTION as CONTACT_QUESTION
from ..excel import ExcelError, PlanRow, Sheet, list_sheets, read_sheet
from ..filler import Summary
from ..fillmode import FillMode
from ..logsetup import setup_logging
from ..update import UpdateCheck
from . import theme
from .preview_table import GRIP, GripDelegate, PreviewTable, TrashDelegate
from .settings_dialog import SettingsDialog
from .update_panel import AVAILABLE_TEXT, UpdateWorker
from .worker import FillWorker, QtLogHandler, ReadWorker

log = logging.getLogger("suunnitelmoittaja.gui")
TIME_FIELD = "suoritusajankohta"
WILMA_SHEET = "Wilma"
SEPARATOR_SHEET = "Välirivi"  # esikatselussa näkyvä tyhjä rivi lähteiden väliin
MANUAL_SHEET = "Oma rivi"  # "+ Uusi rivi" -napilla käsin lisätty rivi
GRIP_COL = 0  # tarttuma raahaukseen
CHECK_COL = 1
SOURCE_COL = 2
FIELD_COLUMN_OFFSET = 3  # 3…6 = kentät
DELETE_COL = 7  # roskakori: poista rivi esikatselusta


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
        # defaultFormat() kunnioittaa QSettings.setDefaultFormat-kutsua (testit ohjaavat
        # asetukset ini-tiedostoon); kaksiargumenttinen muoto menisi Windowsissa aina rekisteriin.
        self.settings = QSettings(
            QSettings.defaultFormat(),
            QSettings.Scope.UserScope,
            "Seise",
            "OpintosuunnitelmanTayttaja",
        )
        self.worker: FillWorker | None = None
        self._available_sheets: list[str] = []
        self._preview_sheets: list[Sheet] = []
        self._preview_rows: list[PreviewRow] = []
        self._edits: dict[tuple[str, int], dict[str, str]] = {}  # key → muokatut kentät
        self._unchecked: set[tuple[str, int]] = set()
        self._order: list[tuple[str, int]] = []  # käyttäjän järjestys, jos riviä siirretty
        self._deleted: set[tuple[str, int]] = set()  # roskakorilla poistetut rivit
        self._wilma_rows: list[PlanRow] = []
        self._wilma_student = ""  # opiskelija, jolta Wilman rivit haettiin
        self._manual_rows: list[dict[str, str]] = []  # "+ Uusi rivi" -rivien lähtöarvot
        self._preview_names: list[
            str
        ] = []  # esikatselun lähteet otsikkoon (Wilma, Excel, Oma rivi…)
        self.reader: ReadWorker | None = None
        self.rb_no_main: QRadioButton | None = None  # "Ei pääsuuntausta Excelistä"
        self.update_check: UpdateCheck | None = None
        self._update_worker: UpdateWorker | None = None

        self.setWindowTitle(APP_TITLE)
        self.resize(1180, 820)

        self._build_menu()
        self._build_ui()
        self._install_log_handler()
        self.reload_config()

        self._chrome_timer = QTimer(self)
        self._chrome_timer.timeout.connect(self._poll_chrome)
        self._chrome_timer.start(2000)
        self._poll_chrome()
        if not os.environ.get("SUUNNITELMOITTAJA_NO_UPDATE_CHECK"):
            QTimer.singleShot(1500, self.check_for_updates_quietly)

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
        act_update = QAction("Tarkista päivitykset…", self)
        act_update.triggered.connect(lambda: self.open_settings(tab="Päivitys"))
        help_menu.addAction(act_update)
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
        self.btn_update_available = QPushButton(AVAILABLE_TEXT)
        self.btn_update_available.setProperty("variant", "link")
        self.btn_update_available.setStyleSheet(
            f"color: {theme.TOKENS['on_section']}; text-decoration: underline; "
            "font-size: 13px; font-weight: 600;"
        )
        self.btn_update_available.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update_available.setToolTip("Uudempi versio on saatavilla. Avaa Päivitys.")
        self.btn_update_available.clicked.connect(lambda: self.open_settings(tab="Päivitys"))
        self.btn_update_available.setVisible(False)
        meta.addWidget(version)
        meta.addWidget(btn_settings, 0, Qt.AlignmentFlag.AlignRight)
        meta.addWidget(self.btn_update_available, 0, Qt.AlignmentFlag.AlignRight)
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
        self.step3_hint = _label(
            "Rivit tulevat esikatseluun Wilmasta, Excelistä tai molemmista. Uudelle "
            "opiskelijalle riittää pääsuuntaus Excelistä; vanhalle hae ensin Wilman rivit ja "
            "täydennä Excelistä.",
            "muted",
        )
        self.step3_hint.setWordWrap(True)
        self.step3_hint.setContentsMargins(0, 0, 0, 14)
        left_layout.addWidget(self.step3_hint)

        # 3a · Wilma
        wilma_title = _label("A · NYKYINEN SUUNNITELMA WILMASTA", "caps")
        wilma_title.setContentsMargins(0, 0, 0, 2)
        left_layout.addWidget(wilma_title)
        wilma_caps = QHBoxLayout()
        wilma_caps.setSpacing(6)
        self.btn_read_wilma = QPushButton("Hae nykyiset rivit Wilmasta")
        self.btn_read_wilma.setProperty("variant", "link")
        self.btn_read_wilma.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_read_wilma.setToolTip(
            "Lukee kohdassa 2 avatun opintosuunnitelmalomakkeen rivit esikatseluun, jossa niitä "
            "voi muokata, järjestää ja yhdistää Excelin riveihin."
        )
        self.btn_read_wilma.clicked.connect(self.read_from_wilma)
        wilma_caps.addWidget(self.btn_read_wilma)
        self.wilma_dot = _label("·", "muted")
        wilma_caps.addWidget(self.wilma_dot)
        self.btn_clear_wilma = QPushButton("Poista")
        self.btn_clear_wilma.setProperty("variant", "link")
        self.btn_clear_wilma.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_wilma.setToolTip("Poista Wilmasta haetut rivit esikatselusta")
        self.btn_clear_wilma.clicked.connect(self.clear_wilma_rows)
        wilma_caps.addWidget(self.btn_clear_wilma)
        wilma_caps.addStretch()
        left_layout.addLayout(wilma_caps)
        self.wilma_status = _label("", "muted")
        self.wilma_status.setWordWrap(True)
        self.wilma_status.setContentsMargins(0, 4, 0, 0)
        left_layout.addWidget(self.wilma_status)
        self._refresh_wilma_status()
        left_layout.addWidget(_hairline(top=12, bottom=10))

        # 3b · Excel
        excel_title = _label("B · POHJA EXCELISTÄ", "caps")
        excel_title.setContentsMargins(0, 0, 0, 2)
        left_layout.addWidget(excel_title)
        excel_caps = QHBoxLayout()
        excel_caps.setSpacing(6)
        self.btn_open_excel = QPushButton("Avaa Excel")
        self.btn_open_excel.setProperty("variant", "link")
        self.btn_open_excel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_excel.setToolTip("Avaa lähde-Excel Excelissä (tai oletusohjelmassa)")
        self.btn_open_excel.clicked.connect(self.open_excel)
        excel_caps.addWidget(self.btn_open_excel)
        excel_caps.addWidget(_label("·", "muted"))
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
        excel_caps.addStretch()
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
        gm.setContentsMargins(0, 14, 0, 0)
        gm.setSpacing(2)
        self.main_caps = _label("PÄÄSUUNTAUS", "caps")
        self.main_caps.setContentsMargins(0, 0, 0, 4)
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
        go.setContentsMargins(0, 12, 0, 0)
        go.setSpacing(2)
        optional_caps = _label("LISÄKSI", "caps")
        optional_caps.setContentsMargins(0, 0, 0, 4)
        go.addWidget(optional_caps)
        self.optional_layout = QVBoxLayout()
        self.optional_layout.setSpacing(0)
        go.addLayout(self.optional_layout)
        left_layout.addWidget(self.group_optional)

        left_layout.addWidget(_hairline(top=14, bottom=10))
        # 3c · Muut valinnat
        other_caps = _label("C · MUUT VALINNAT", "caps")
        other_caps.setContentsMargins(0, 0, 0, 4)
        left_layout.addWidget(other_caps)
        self.manual_toggle = QCheckBox("Valitse välilehdet käsin")
        self.manual_toggle.toggled.connect(self._toggle_manual)
        left_layout.addWidget(self.manual_toggle)
        self.manual_list = QListWidget()
        self.manual_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.manual_list.itemChanged.connect(lambda _item: self.update_preview())
        self.manual_list.setVisible(False)
        self.manual_list.setMaximumHeight(190)
        left_layout.addWidget(self.manual_list)
        self.separator_check = QCheckBox("Tyhjä välirivi lähteiden väliin")
        self.separator_check.toggled.connect(lambda _c: self.update_preview())
        left_layout.addWidget(self.separator_check)
        self.update_row_check = QCheckBox("Lisää päivitysmerkintä (Pvm & päivittäjä)")
        self.update_row_check.setToolTip(
            "Täytön lopuksi Pvm & päivittäjä -taulukkoon lisätään rivi: tämän päivän "
            "päivämäärä ja kirjautunut opettaja Wilman oletuksesta. Tarkista rivi ennen "
            "tallennusta."
        )
        left_layout.addWidget(self.update_row_check)
        self.contact_check = QCheckBox(CONTACT_QUESTION.rstrip("?"))
        self.contact_check.toggled.connect(lambda _c: self.update_preview())
        left_layout.addWidget(self.contact_check)
        self.contact_hint = _label("", "muted")
        self.contact_hint.setWordWrap(True)
        left_layout.addWidget(self.contact_hint)
        left_layout.addStretch()

        # 4 · Esikatselu ja muokkaus
        step4 = self._step_header("4", "Esikatselu ja muokkaus")
        self.btn_add_row = QPushButton("+ Uusi rivi")
        self.btn_add_row.setProperty("variant", "link")
        self.btn_add_row.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_row.setToolTip(
            "Lisää esikatseluun tyhjä rivi (lähde 'Oma rivi') valitun rivin alle, tai loppuun. "
            "Kirjoita solut kaksoisnapsauttamalla."
        )
        self.btn_add_row.clicked.connect(self.add_manual_row)
        step4.addWidget(self.btn_add_row)
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
        self.restore_dot = _label("·", "muted")
        step4.addWidget(self.restore_dot)
        self.btn_restore = QPushButton("Palauta poistetut")
        self.btn_restore.setProperty("variant", "link")
        self.btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore.setToolTip("Palauta roskakorilla poistetut rivit esikatseluun")
        self.btn_restore.clicked.connect(self.restore_deleted_rows)
        step4.addWidget(self.btn_restore)
        self.restore_dot.setVisible(False)
        self.btn_restore.setVisible(False)
        step4.addStretch()
        self.preview_label = _label("", "caps")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        step4.addWidget(self.preview_label)
        right_layout.addLayout(step4)
        self.preview = PreviewTable(0, 8)
        self.preview.setHorizontalHeaderLabels(
            ["", "", "Lähde", "Osaamistavoite", "Laajuus", "Suoritustapa", "Ajankohta", ""]
        )
        self.preview.row_moved.connect(self.move_row)
        self.preview.cellClicked.connect(self._on_preview_cell_clicked)
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
        hh.setSectionResizeMode(DELETE_COL, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(DELETE_COL, 36)
        self.preview.setItemDelegateForColumn(
            DELETE_COL, TrashDelegate(theme.TOKENS["ink_soft"], self.preview)
        )
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
        right_layout.addWidget(self.preview, 6)

        right_layout.addWidget(_hairline(top=14, bottom=14))

        # 5 · Täyttö
        step5 = self._step_header("5", "Täyttö")
        right_layout.addLayout(step5)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(18)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_caps = _label("TÄYTTÖTAPA", "caps")
        mode_caps.setContentsMargins(0, 0, 8, 0)
        mode_row.addWidget(mode_caps)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_append = QRadioButton("Lisää lomakkeen loppuun")
        self.mode_replace = QRadioButton("Korvaa lomakkeen nykyiset rivit")
        self.mode_complete = QRadioButton("Täydennä puuttuvat")
        self.mode_buttons: dict[FillMode, QRadioButton] = {
            FillMode.APPEND: self.mode_append,
            FillMode.REPLACE: self.mode_replace,
            FillMode.COMPLETE: self.mode_complete,
        }
        for mode, rb in self.mode_buttons.items():
            rb.setProperty("mode", mode.value)
            rb.setToolTip(mode.description)
            rb.toggled.connect(self._on_mode_changed)
            self.mode_group.addButton(rb)
            mode_row.addWidget(rb)
        self.mode_replace.setToolTip(
            "Kirjoittaa esikatselun rivit lomakkeen nykyisten rivien päälle. Käytä tätä, kun "
            "olet hakenut rivit Wilmasta ja muokannut niitä. Wilmassa tallennettuja rivejä ei "
            "voi poistaa napilla, joten ylijäävät jäävät tyhjiksi."
        )
        mode_row.addStretch()
        right_layout.addLayout(mode_row)
        self.mode_hint = _label("", "muted")
        self.mode_hint.setWordWrap(True)
        self.mode_hint.setContentsMargins(0, 4, 0, 8)
        right_layout.addWidget(self.mode_hint)
        # oletusvalinta asetetaan reload_configissa (QSettings → config.fill_mode)
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
        right_layout.addSpacing(10)
        right_layout.addWidget(self.progress)
        right_layout.addSpacing(10)
        self.log_view = QPlainTextEdit()
        self.log_view.setProperty("role", "log")
        self.log_view.setReadOnly(True)
        self.log_view.setFrameShape(QFrame.Shape.NoFrame)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setMinimumHeight(80)
        self.log_view.setMaximumHeight(170)
        self.log_view.setPlaceholderText("Täytön loki näkyy tässä.")
        right_layout.addWidget(self.log_view, 1)

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
        self.update_row_check.setChecked(self.config.add_update_row)
        saved_mode = str(self.settings.value("fill_mode", "", type=str) or "")
        self.set_fill_mode(FillMode.parse(saved_mode, default=self.config.fill_mode))
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
        self.rb_no_main = None
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
            # Vaihtoehto pääsuuntaukselle: vain Wilman rivit (ja lisävalinnat)
            self.rb_no_main = QRadioButton("Ei pääsuuntausta Excelistä")
            self.rb_no_main.setToolTip(
                "Käytä, kun opiskelijalla on jo suunnitelma Wilmassa: hae rivit Wilmasta, "
                "ja ota Excelistä vain lisävalinnat. Pääsuuntauksen voi silti valita."
            )
            self.rb_no_main.toggled.connect(lambda _c: self.update_preview())
            self.main_group.addButton(self.rb_no_main)
            self.main_layout.addWidget(self.rb_no_main)
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

    def selected_fill_mode(self) -> FillMode:
        checked = self.mode_group.checkedButton()
        if checked is None:
            return self.config.fill_mode
        return FillMode.parse(checked.property("mode"), default=self.config.fill_mode)

    def set_fill_mode(self, mode: FillMode) -> None:
        self.mode_buttons[mode].setChecked(True)

    def _on_mode_changed(self, checked: bool) -> None:
        if not checked:
            return
        mode = self.selected_fill_mode()
        self.mode_hint.setText(mode.description)
        self.settings.setValue("fill_mode", mode.value)

    def selected_sheet_names(self) -> list[str]:
        if self.manual_toggle.isChecked():
            return [
                self.manual_list.item(i).text()
                for i in range(self.manual_list.count())
                if self.manual_list.item(i).checkState() == Qt.CheckState.Checked
            ]
        chosen: list[str] = []
        checked = self.main_group.checkedButton()
        if checked is not None and checked is not self.rb_no_main:
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
        for i, values in enumerate(self._manual_rows):
            rows.append(PreviewRow(MANUAL_SHEET, (MANUAL_SHEET, i), dict(values)))
        if self._manual_rows:
            names = [*names, MANUAL_SHEET]
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

        if self.separator_check.isChecked():
            rows = self._with_separator_rows(rows)
        rows = [r for r in rows if r.key not in self._deleted]
        for row in rows:
            row.values.update(self._edits.get(row.key, {}))
            row.checked = row.key not in self._unchecked
        if self._order:
            # käyttäjän järjestys; uudet (esim. juuri lisätyt välirivit tai Excelin rivit)
            # jäävät luonnollisen edeltäjänsä perään
            pos: dict[tuple[str, int], float] = {k: float(i) for i, k in enumerate(self._order)}
            prev = -1.0
            for row in rows:
                if row.key in pos:
                    prev = pos[row.key]
                else:
                    prev += 0.001
                    pos[row.key] = prev
            rows.sort(key=lambda r: pos[r.key])
        self._preview_rows = rows
        self._preview_names = names
        self._render_preview()
        self._refresh_preview_summary(names)
        self._refresh_restore_link()

    def _with_separator_rows(self, rows: list[PreviewRow]) -> list[PreviewRow]:
        """Lisää tyhjä välirivi jokaiseen kohtaan, jossa lähde vaihtuu."""
        out: list[PreviewRow] = []
        n = 0
        for row in rows:
            # Oma rivi liittyy naapuriinsa: sen ympärille ei tule väliriviä
            if (
                out
                and out[-1].sheet != row.sheet
                and MANUAL_SHEET not in (out[-1].sheet, row.sheet)
            ):
                out.append(
                    PreviewRow(
                        SEPARATOR_SHEET,
                        (SEPARATOR_SHEET, n),
                        dict.fromkeys(self.config.field_names, ""),
                    )
                )
                n += 1
            out.append(row)
        return out

    def _refresh_restore_link(self) -> None:
        visible = bool(self._deleted)
        self.btn_restore.setVisible(visible)
        self.restore_dot.setVisible(visible)
        if visible:
            self.btn_restore.setText(f"Palauta poistetut ({len(self._deleted)})")

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
            trash = QTableWidgetItem()
            trash.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            trash.setToolTip("Poista rivi esikatselusta (ei täytetä lomakkeelle)")
            self.preview.setItem(r, DELETE_COL, trash)
        self.preview.blockSignals(False)

    def _on_preview_cell_clicked(self, r: int, col: int) -> None:
        if col == DELETE_COL:
            self.delete_row(r)

    def delete_row(self, r: int) -> None:
        """Poista rivi esikatselusta roskakorilla. Palautettavissa 'Palauta poistetut' -linkistä."""
        if not 0 <= r < len(self._preview_rows):
            return
        row = self._preview_rows.pop(r)
        self._deleted.add(row.key)
        if self._order:
            self._order = [k for k in self._order if k != row.key]
        self._render_preview()
        if self.preview.rowCount():
            self.preview.selectRow(min(r, self.preview.rowCount() - 1))
        self._refresh_preview_summary()
        self._refresh_restore_link()
        self.statusBar().showMessage(
            f"Rivi poistettu esikatselusta: {row.values.get(self.config.field_names[0], '')}", 4000
        )

    def restore_deleted_rows(self) -> None:
        self._deleted.clear()
        self.update_preview()

    def add_manual_row(self) -> int:
        """Lisää tyhjä "Oma rivi" esikatseluun valitun rivin alle (tai loppuun) ja avaa
        osaamistavoitesolun muokattavaksi. Palauttaa rivin indeksin esikatselussa."""
        key = (MANUAL_SHEET, len(self._manual_rows))
        self._manual_rows.append(dict.fromkeys(self.config.field_names, ""))
        sel = self.preview.selectionModel()
        current = self.preview.currentRow() if sel is not None and sel.hasSelection() else -1
        self.update_preview()
        idx = next(i for i, r in enumerate(self._preview_rows) if r.key == key)
        # valitun rivin alle, muuten loppuun (myös silloin, kun rivejä on jo järjestelty)
        dst = current + 1 if current >= 0 else len(self._preview_rows) - 1
        if dst != idx:
            self.move_row(idx, dst)
            idx = dst
        self.preview.selectRow(idx)
        first = self.preview.item(idx, FIELD_COLUMN_OFFSET)
        if first is not None:
            self.preview.setCurrentItem(first)
            self.preview.editItem(first)
        self.statusBar().showMessage(
            "Uusi rivi lisätty. Kirjoita solut kaksoisnapsauttamalla.", 5000
        )
        return idx

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
        self._refresh_preview_summary()

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
    def _on_wilma_rows(self, rows: list[PlanRow], student: str = "") -> None:
        self._wilma_rows = list(rows)
        self._wilma_student = student
        # vanhat Wilma-muokkaukset eivät enää vastaa uutta lukua
        for key in [k for k in self._edits if k[0] == WILMA_SHEET]:
            del self._edits[key]
        self._unchecked = {k for k in self._unchecked if k[0] != WILMA_SHEET}
        self._deleted = {k for k in self._deleted if k[0] != WILMA_SHEET}
        self._order = []
        if rows and self.rb_no_main is not None and not self.manual_toggle.isChecked():
            # Wilman rivit korvaavat pääsuuntauksen; Excelin suuntauksen voi valita takaisin
            self.rb_no_main.setChecked(True)
        self.update_preview()
        self._refresh_wilma_status()
        if rows:
            self.mode_replace.setChecked(True)
            self.statusBar().showMessage(
                f"Luettiin {len(rows)} riviä Wilmasta. Täyttötila: korvaa nykyiset rivit.", 6000
            )
        else:
            self.statusBar().showMessage("Lomakkeella ei ole rivejä.", 4000)

    def _refresh_wilma_status(self) -> None:
        n = len(self._wilma_rows)
        if n:
            who = f" opiskelijalta {self._wilma_student}" if self._wilma_student else ""
            self.wilma_status.setText(
                f"{n} riviä haettu{who}. Ne näkyvät esikatselussa lähteenä Wilma; muokkaa ja "
                "järjestä ne kohdassa 4. Valitse pääsuuntaus, jos haluat lisätä Excelin rivit."
            )
        else:
            self.wilma_status.setText(
                "Ei haettu. Lukee kohdassa 2 avatun lomakkeen rivit esikatseluun, jolloin "
                "nykyistä suunnitelmaa voi muokata ja täydentää."
            )
        self.btn_clear_wilma.setVisible(n > 0)
        self.wilma_dot.setVisible(n > 0)

    @Slot(str)
    def _on_wilma_failed(self, message: str) -> None:
        log.error(message)
        QMessageBox.critical(self, "Luku epäonnistui", message)

    def _on_reader_done(self) -> None:
        self.reader = None
        self.btn_read_wilma.setEnabled(True)

    def clear_wilma_rows(self) -> None:
        self._wilma_rows = []
        self._wilma_student = ""
        self._order = []
        if self.rb_no_main is not None and self.rb_no_main.isChecked():
            # ilman Wilman rivejä palataan ensimmäiseen pääsuuntaukseen
            self.main_group.buttons()[0].setChecked(True)
        self.update_preview()
        self._refresh_wilma_status()

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
        self._refresh_preview_summary()

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
            self._refresh_preview_summary()
            return
        field = self._field_for_column(item.column())
        if field is not None:
            self._record_edit(r, field, item.text().strip())

    def _refresh_preview_summary(self, names: list[str] | None = None) -> None:
        names = self._preview_names if names is None else names
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

    def open_excel(self) -> None:
        """Avaa lähde-Excel käyttöjärjestelmän oletusohjelmassa (Excel)."""
        if not self.excel_path.exists():
            QMessageBox.information(
                self, "Excel ei löydy", f"Tiedostoa ei ole:\n{self.excel_path}\n\nValitse Vaihda."
            )
            return
        self._open_path(self.excel_path)
        self.statusBar().showMessage(
            f"Avattu {self.excel_path.name}. Tallenna Excel ja paina Lataa uudelleen.", 6000
        )

    def check_for_updates_quietly(self) -> None:
        """Taustatarkistus käynnistyksessä: näyttää linkin, jos uudempi versio on saatavilla.

        Virheet (ei verkkoa, ei gitiä) menevät vain lokiin, käyttäjää ei häiritä.
        """
        if self._update_worker is not None:
            return
        self._update_worker = UpdateWorker("check", self)
        self._update_worker.checked.connect(self._on_update_checked)
        self._update_worker.failed.connect(
            lambda msg: log.debug("Päivitystarkistus ohitettiin: %s", msg)
        )
        self._update_worker.finished.connect(self._on_update_worker_done)
        self._update_worker.start()

    @Slot(object)
    def _on_update_checked(self, check: UpdateCheck) -> None:
        self.update_check = check
        self.btn_update_available.setVisible(check.available)
        if check.available:
            log.info("%s: %s", AVAILABLE_TEXT, check.summary)
            self.statusBar().showMessage(f"{AVAILABLE_TEXT}{theme.MIDDOT}{check.summary}", 8000)

    def _on_update_worker_done(self) -> None:
        self._update_worker = None

    def open_settings(self, tab: str | None = None) -> None:
        dialog = SettingsDialog(
            self.config, self.config_path, self, tab=tab, update_check=self.update_check
        )
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
        mode = self.selected_fill_mode()
        # Väärän opiskelijan suoja: katso, kenen lomake Chromessa on auki, ja näytä nimi
        try:
            student = self._probe_student()
        except BrowserError as exc:
            QMessageBox.warning(self, "Lomaketta ei löydy", str(exc))
            return
        who = (
            f"OPISKELIJA: {student}\n\n"
            if student
            else "Opiskelijan nimeä ei tunnistettu lomakesivulta – tarkista välilehti.\n\n"
        )
        if student and self._wilma_student and self._wilma_student != student:
            who += (
                f"HUOM. Wilman rivit haettiin opiskelijalta {self._wilma_student}, mutta "
                f"Chromessa on auki {student}.\n\n"
            )
        text = (
            f"{who}Täytetään {total} riviä lähteistä:\n{', '.join(s.name for s in sheets)}\n\n"
            f"Täyttötapa: {mode.label}.\n{mode.description}"
            + (
                "\n\nLopuksi lisätään Pvm & päivittäjä -merkintä."
                if self.update_row_check.isChecked()
                else ""
            )
        )
        if mode is FillMode.REPLACE:
            answer = QMessageBox.warning(
                self,
                "Korvataanko lomakkeen rivit?",
                text + "\n\nLomakkeen nykyiset rivit KORVATAAN esikatselun riveillä.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            answer = QMessageBox.question(self, "Täytetäänkö lomake?", text)
        if answer != QMessageBox.StandardButton.Yes:
            return

        # Välirivit ovat jo esikatselun riveinä (lähde "Välirivi"), joten täyttäjä ei lisää omiaan
        config = replace(self.config, separator_row_between_sheets=False)
        self.log_view.clear()
        self.progress.setMaximum(total)
        self.progress.setValue(0)
        self.progress_label.setText(f"0 / {total} riviä")
        self.worker = FillWorker(
            config, sheets, mode=mode, update_row=self.update_row_check.isChecked()
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_done)
        self._set_running(True)
        self.worker.start()

    def _probe_student(self) -> str:
        """Kenen opintosuunnitelma Chromessa on auki. Nostaa BrowserError, jos lomaketta ei ole."""
        with connect(self.config.browser) as browser:
            page = find_form_page(browser, self.config.browser, self.config.selectors.table_body)
            return student_name(page)

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
        for rb in self.mode_buttons.values():
            rb.setEnabled(not running)
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
            + (f", ohitettu {s.skipped_rows} (jo lomakkeella)" if s.skipped_rows else "")
            for s in summary.sheets
        ]
        text = (
            (f"Opiskelija: {summary.student}\n" if summary.student else "")
            + f"Täyttötapa: {summary.mode.label}\n\n"
            + "\n".join(lines)
            + (f"\n\nYhteensä {summary.successful_rows}/{summary.total_rows} riviä onnistui.")
        )
        if summary.skipped_rows:
            text += f"\nOhitettu {summary.skipped_rows} riviä, jotka olivat jo lomakkeella."
        if summary.removed_rows:
            text += f"\nPoistettu {summary.removed_rows} riviä poistonapilla."
        if summary.cleared_rows:
            text += (
                f"\nLomakkeen loppuun jäi {summary.cleared_rows} tyhjää riviä. "
                "Poista ne Wilmassa käsin ennen tallennusta."
            )
        if summary.update_row:
            text += f"\nPvm & päivittäjä -merkintä lisätty: {summary.update_row}."
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
