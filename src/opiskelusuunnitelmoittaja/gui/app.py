"""GUI:n käynnistys: ``suunnitelmoittaja-gui`` tai paketoitu sovellus."""

from __future__ import annotations

import sys
from pathlib import Path

from .. import APP_TITLE
from ..paths import ensure_user_files, resource_path, user_config_path


def icon_path() -> Path | None:
    """Sovelluskuvake: paketissa juuressa, kehityksessä packaging/-kansiossa.

    Windowsissa monikokoinen .ico, jonka 16–48 px:n koot on piirretty teräviksi tehtäväpalkkia
    varten; muualla 1024 px:n PNG (macOS:n Dock).
    """
    names = ("icon.ico", "icon.png") if sys.platform == "win32" else ("icon.png",)
    for name in names:
        for candidate in (resource_path(name), resource_path("packaging") / name):
            if candidate.exists():
                return candidate
    return None


def resolve_config_path(argv: list[str]) -> Path:
    """Asetustiedosto: argumentti tai käyttäjän oma data-hakemisto.

    GUI ei kirjoita repon config.jsoniin edes kehitysajossa, jotta opettajan yhteystiedot
    eivät päädy versionhallintaan. Ensimmäisellä käynnistyksellä repon (tai paketin)
    config.json ja Excel kopioidaan pohjaksi käyttäjän hakemistoon.
    """
    if len(argv) > 1 and argv[1].endswith(".json"):
        return Path(argv[1]).expanduser().resolve()
    ensure_user_files()
    return user_config_path()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--cli" in argv:
        # Paketoitu sovellus komentoriviltä: OpintosuunnitelmanTayttaja --cli fill 1
        from ..cli import main as cli_main

        rest = [a for a in argv[1:] if a != "--cli"]
        return cli_main(rest)

    from PySide6.QtWidgets import QApplication

    from . import theme
    from .main_window import MainWindow

    app = QApplication(argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    app.setOrganizationName("Seise")
    theme.apply(app)
    icon = icon_path()
    if icon is not None:
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow(resolve_config_path(argv))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
