"""Asetusdialogi: yleiset, ohjattu kysely, lomakkeen valitsimet."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import BrowserConfig, Config, Selectors, save_config
from ..wizard import OptionalSheet, WizardConfig
from .theme import MIDDOT


class SettingsDialog(QDialog):
    def __init__(self, config: Config, config_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Asetukset")
        self.resize(720, 560)
        self.config = config
        self.config_path = config_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(14)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        tabs.addTab(self._build_general(), "Yleiset")
        tabs.addTab(self._build_wizard(), "Kysely")
        tabs.addTab(self._build_selectors(), "Lomake")

        path_label = QLabel(f"Tallennetaan tiedostoon{MIDDOT}{config_path}")
        path_label.setProperty("role", "muted")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.setText("Tallenna")
        save_btn.setProperty("variant", "primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Peruuta")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ välilehdet

    def _build_general(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        b = self.config.browser
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(b.remote_debugging_port)
        form.addRow("Chromen etädebuggausportti", self.port)
        self.timeout = QSpinBox()
        self.timeout.setRange(1000, 120_000)
        self.timeout.setSingleStep(1000)
        self.timeout.setSuffix(" ms")
        self.timeout.setValue(b.timeout_ms)
        form.addRow("Odotusaika elementeille", self.timeout)
        self.url_contains = QLineEdit(b.page_url_contains)
        self.url_contains.setPlaceholderText(
            "esim. wilma – tyhjä = etsi lomake sisällön perusteella"
        )
        form.addRow("Lomakesivun osoite sisältää", self.url_contains)
        self.chrome_path = QLineEdit(b.chrome_path)
        self.chrome_path.setPlaceholderText("tyhjä = tunnistetaan automaattisesti")
        form.addRow("Chromen polku", self.chrome_path)
        self.user_data_dir = QLineEdit(b.user_data_dir)
        self.user_data_dir.setPlaceholderText("tyhjä = ~/.opiskelusuunnitelmoittaja/chrome-profile")
        form.addRow("Chrome-profiilin kansio", self.user_data_dir)

        self.empty_value = QLineEdit(self.config.empty_value)
        self.empty_value.setPlaceholderText("oletus välilyönti – lomake ei hyväksy tyhjää")
        form.addRow("Tyhjän solun arvo lomakkeella", self.empty_value)
        self.separator = QCheckBox("Tyhjä välirivi välilehtien väliin")
        self.separator.setChecked(self.config.separator_row_between_sheets)
        form.addRow("", self.separator)
        self.max_attempts = QSpinBox()
        self.max_attempts.setRange(1, 10)
        self.max_attempts.setValue(self.config.max_attempts)
        form.addRow("Uudelleenyrityksiä", self.max_attempts)
        return w

    def _build_wizard(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        wizard = self.config.wizard or WizardConfig()
        form = QFormLayout()
        self.main_question = QLineEdit(wizard.main_question)
        form.addRow("Pääsuuntauksen kysymys", self.main_question)
        self.main_sheets = QPlainTextEdit("\n".join(wizard.main_sheets))
        self.main_sheets.setPlaceholderText("Yksi välilehden nimi per rivi")
        self.main_sheets.setMaximumHeight(90)
        form.addRow("Pääsuuntaukset (välilehdet)", self.main_sheets)
        layout.addLayout(form)

        layout.addWidget(QLabel("Kyllä/ei-kysymykset (järjestys = täyttöjärjestys):"))
        self.optional = QTableWidget(0, 3)
        self.optional.setHorizontalHeaderLabels(["Välilehti", "Kysymys", "Oletus kyllä"])
        self.optional.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.optional.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for opt in wizard.optional_sheets:
            self._add_optional_row(opt.sheet, opt.question, opt.default)
        layout.addWidget(self.optional, 1)

        buttons = QHBoxLayout()
        btn_add = QPushButton("Lisää")
        btn_add.clicked.connect(lambda: self._add_optional_row("", "", False))
        btn_del = QPushButton("Poista")
        btn_del.clicked.connect(self._remove_optional_row)
        btn_up = QPushButton("▲")
        btn_up.clicked.connect(lambda: self._move_optional_row(-1))
        btn_down = QPushButton("▼")
        btn_down.clicked.connect(lambda: self._move_optional_row(1))
        for b in (btn_add, btn_del, btn_up, btn_down):
            buttons.addWidget(b)
        buttons.addStretch()
        layout.addLayout(buttons)
        return w

    def _build_selectors(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        s = self.config.selectors
        self.table_body = QLineEdit(s.table_body)
        form.addRow("Taulukon tbody (CSS)", self.table_body)
        self.add_row_button = QLineEdit(s.add_row_button)
        form.addRow("Lisää rivi -nappi", self.add_row_button)
        self.input_in_cell = QLineEdit(s.input_in_cell)
        form.addRow("Kenttä solun sisällä", self.input_in_cell)
        form.addRow(QLabel("Solut ja Excel-otsikot kentittäin:"))
        self.field_rows: dict[str, tuple[QLineEdit, QLineEdit]] = {}
        for field in self.config.field_names:
            cell = QLineEdit(s.field_cells.get(field, ""))
            column = QLineEdit(self.config.excel_columns.get(field, ""))
            row = QHBoxLayout()
            row.addWidget(QLabel("solu"))
            row.addWidget(cell, 1)
            row.addWidget(QLabel("Excel-otsikko"))
            row.addWidget(column, 2)
            holder = QWidget()
            holder.setLayout(row)
            form.addRow(field, holder)
            self.field_rows[field] = (cell, column)
        return w

    # ------------------------------------------------------------------ apurit

    def _add_optional_row(self, sheet: str, question: str, default: bool) -> None:
        r = self.optional.rowCount()
        self.optional.insertRow(r)
        self.optional.setItem(r, 0, QTableWidgetItem(sheet))
        self.optional.setItem(r, 1, QTableWidgetItem(question))
        flag = QTableWidgetItem()
        flag.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        flag.setCheckState(Qt.CheckState.Checked if default else Qt.CheckState.Unchecked)
        self.optional.setItem(r, 2, flag)

    def _remove_optional_row(self) -> None:
        row = self.optional.currentRow()
        if row >= 0:
            self.optional.removeRow(row)

    def _move_optional_row(self, delta: int) -> None:
        row = self.optional.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self.optional.rowCount():
            return
        for col in range(3):
            a = self.optional.takeItem(row, col)
            b = self.optional.takeItem(target, col)
            self.optional.setItem(row, col, b)
            self.optional.setItem(target, col, a)
        self.optional.setCurrentCell(target, 0)

    def _collect_optional(self) -> list[OptionalSheet]:
        result: list[OptionalSheet] = []
        for r in range(self.optional.rowCount()):
            sheet_item = self.optional.item(r, 0)
            question_item = self.optional.item(r, 1)
            flag_item = self.optional.item(r, 2)
            sheet = sheet_item.text().strip() if sheet_item else ""
            if not sheet:
                continue
            question = (
                question_item.text().strip() if question_item else ""
            ) or f"Lisätäänkö {sheet}?"
            default = bool(flag_item and flag_item.checkState() == Qt.CheckState.Checked)
            result.append(OptionalSheet(sheet, question, default))
        return result

    def build_config(self) -> Config:
        mains = [
            line.strip() for line in self.main_sheets.toPlainText().splitlines() if line.strip()
        ]
        wizard = WizardConfig(
            main_question=self.main_question.text().strip() or WizardConfig.main_question,
            main_sheets=mains,
            optional_sheets=self._collect_optional(),
        )
        field_cells = {f: cell.text().strip() for f, (cell, _c) in self.field_rows.items()}
        excel_columns = {f: col.text().strip() for f, (_c, col) in self.field_rows.items()}
        return replace(
            self.config,
            browser=BrowserConfig(
                remote_debugging_port=self.port.value(),
                user_data_dir=self.user_data_dir.text().strip(),
                chrome_path=self.chrome_path.text().strip(),
                page_url_contains=self.url_contains.text().strip(),
                timeout_ms=self.timeout.value(),
            ),
            selectors=Selectors(
                table_body=self.table_body.text().strip(),
                add_row_button=self.add_row_button.text().strip(),
                field_cells=field_cells,
                input_in_cell=self.input_in_cell.text().strip(),
            ),
            excel_columns=excel_columns,
            empty_value=self.empty_value.text(),
            separator_row_between_sheets=self.separator.isChecked(),
            max_attempts=self.max_attempts.value(),
            wizard=wizard if mains else None,
        )

    def save(self) -> None:
        config = self.build_config()
        if not config.selectors.table_body or not config.selectors.add_row_button:
            QMessageBox.warning(
                self, "Puuttuva arvo", "Taulukon ja lisäysnapin valitsimet ovat pakollisia."
            )
            return
        try:
            save_config(config, self.config_path)
        except OSError as exc:
            QMessageBox.critical(self, "Tallennus epäonnistui", str(exc))
            return
        self.accept()
