"""PyInstaller-käynnistin: absoluuttinen import, jotta paketin suhteelliset importit toimivat."""

import sys

from opiskelusuunnitelmoittaja.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
