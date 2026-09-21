"""Asetusten Päivitys-välilehti: tarkista ja hae uusin versio (git tai Releases)."""

from __future__ import annotations

import traceback
import webbrowser

from PySide6.QtCore import QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..update import (
    RELEASES_URL,
    UpdateCheck,
    UpdateError,
    apply_update,
    check_for_update,
    repo_root,
    restart_application,
)
from .theme import MIDDOT


class UpdateWorker(QThread):
    """Ajaa tarkistuksen tai päivityksen taustalla, jotta ikkuna ei jäädy."""

    checked = Signal(object)  # UpdateCheck
    applied = Signal(str)  # yhteenveto
    failed = Signal(str)
    log = Signal(str)

    def __init__(self, action: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.action = action

    def run(self) -> None:
        try:
            if self.action == "check":
                self.checked.emit(check_for_update())
            else:
                self.applied.emit(apply_update(log=self.log.emit))
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.log.emit(traceback.format_exc())
            self.failed.emit(f"Odottamaton virhe: {exc}")


class UpdatePanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.worker: UpdateWorker | None = None
        self.check: UpdateCheck | None = None
        self.root = repo_root()

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        kind = (
            f"kehitysversio gitistä{MIDDOT}{self.root}"
            if self.root is not None
            else f"paketoitu sovellus{MIDDOT}päivitykset Releases-sivulta"
        )
        self.version_label = QLabel(f"Versio {__version__}{MIDDOT}{kind}")
        self.version_label.setWordWrap(True)
        layout.addWidget(self.version_label)

        self.status_label = QLabel("Päivityksiä ei ole vielä tarkistettu.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.btn_check = QPushButton("Tarkista päivitykset")
        self.btn_check.clicked.connect(self.start_check)
        buttons.addWidget(self.btn_check)
        self.btn_update = QPushButton("Päivitä" if self.root is not None else "Avaa lataussivu")
        self.btn_update.setProperty("variant", "primary")
        self.btn_update.setEnabled(False)
        self.btn_update.clicked.connect(self.start_update)
        buttons.addWidget(self.btn_update)
        buttons.addStretch()
        layout.addLayout(buttons)

        hint = QLabel(
            "Kehitysversio: git pull --ff-only repokansiossa ja uv sync, minkä jälkeen sovellus "
            "käynnistetään uudelleen. Paketoitu sovellus: uusi paketti ladataan GitHubista."
            if self.root is not None
            else f"Uusimmat paketit: {RELEASES_URL}"
        )
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.log_view = QPlainTextEdit()
        self.log_view.setProperty("role", "log")
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Tarkistuksen ja päivityksen loki näkyy tässä.")
        layout.addWidget(self.log_view, 1)

    # ------------------------------------------------------------------ toiminnot

    def start_check(self) -> None:
        if self.worker is not None:
            return
        self.status_label.setText("Tarkistetaan…")
        self.log_view.clear()
        self._run("check")

    def start_update(self) -> None:
        if self.worker is not None:
            return
        if self.root is None:
            webbrowser.open(self.check.url if self.check else RELEASES_URL)
            return
        if self.check is not None and self.check.warnings:
            answer = QMessageBox.question(
                self,
                "Päivitetäänkö silti?",
                "\n".join(self.check.warnings)
                + "\n\nPaikalliset muutokset voivat estää päivityksen (git pull --ff-only). "
                "Jatketaanko?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.status_label.setText("Päivitetään…")
        self._run("apply")

    def _run(self, action: str) -> None:
        self.worker = UpdateWorker(action, self)
        self.worker.checked.connect(self._on_checked)
        self.worker.applied.connect(self._on_applied)
        self.worker.failed.connect(self._on_failed)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.finished.connect(self._on_done)
        self.btn_check.setEnabled(False)
        self.btn_update.setEnabled(False)
        self.worker.start()

    @Slot(object)
    def _on_checked(self, check: UpdateCheck) -> None:
        self.check = check
        self.status_label.setText(check.summary)
        if check.details:
            self.log_view.appendPlainText(check.details)
        for warning in check.warnings:
            self.log_view.appendPlainText(f"Huom. {warning}")
        self._update_button_enabled = check.available or self.root is None

    @Slot(str)
    def _on_applied(self, message: str) -> None:
        self.status_label.setText(message.splitlines()[0])
        self.log_view.appendPlainText(message)
        self.check = None
        self._update_button_enabled = False
        if message.startswith("Ei uusia"):
            return
        answer = QMessageBox.question(
            self,
            "Päivitys valmis",
            message + "\n\nKäynnistetäänkö sovellus uudelleen nyt?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.restart()

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.status_label.setText("Epäonnistui – katso loki.")
        self.log_view.appendPlainText(message)
        QMessageBox.warning(self, "Päivitys", message)
        self._update_button_enabled = bool(self.check and self.check.available)

    def _on_done(self) -> None:
        self.worker = None
        self.btn_check.setEnabled(True)
        self.btn_update.setEnabled(getattr(self, "_update_button_enabled", False))

    def restart(self) -> None:
        try:
            restart_application(self.root)
        except Exception as exc:
            QMessageBox.warning(self, "Uudelleenkäynnistys", f"Ei onnistunut: {exc}")
            return
        app = QApplication.instance()
        if isinstance(app, QApplication):
            QTimer.singleShot(0, app.closeAllWindows)
            QTimer.singleShot(100, app.quit)
