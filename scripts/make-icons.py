"""Sovelluskuvake "Raahattava rivi" (konsepti D, lokakuu 2026) kaikkiin tarvittaviin kokoihin.

Aja repon juuresta:
    .venv/bin/python -I scripts/make-icons.py

Kirjoittaa:
    packaging/icon.png   1024 px, Applen ruudukko (runko 824 px keskellä); ajonaikainen
                         ikkunakuvake ja PyInstallerin lähde muilla kuin Windowsilla
    packaging/icon.icns  macOS: 16–1024 px (@1x ja @2x), tehdään iconutililla (vain macOS)
    packaging/icon.ico   Windows: 16, 20, 24, 32, 40, 48, 64, 128 ja 256 px

Jokainen koko piirretään suoraan vektorista eikä pienennetä 1024 px:n kuvasta. Muodot ovat
16 × 16 -ruudukossa, ja niiden reunat pyöristetään kokonaisiin pikseleihin, joten 16–48 px:n
kuvakkeet pysyvät terävinä. Windowsin kuvakkeessa runko täyttää lähes koko ruudun (1/16 reunus),
jolloin kuvake erottuu tehtäväpalkissa paremmin; macOS:ssä noudatetaan Applen ruudukkoa.
Luonnokset ja vertailu: packaging/icon-variants/2026-10-luonnokset/.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath

PACKAGING = Path(__file__).resolve().parents[1] / "packaging"

# BC Helsinki -tokenit (gui/theme.py)
PERG = "#F4ECDD"
BURG = "#69013B"
KULTA = "#9C7A3A"

# Rivit 16 × 16 -ruudukon yksiköissä: (x0, y0, x1, y1, väri). Kaksi saraketta
# (järjestysnumero | sisältö) erottaa taulukon ≡-valikkokuvakkeesta; keskimmäinen rivi on
# kullalla ja yhden yksikön oikealla, eli sitä raahataan.
RIVIT = [
    (3, 4, 5, 6, PERG),
    (6, 4, 12, 6, PERG),
    (4, 7, 6, 9, KULTA),
    (7, 7, 13, 9, KULTA),
    (3, 10, 5, 12, PERG),
    (6, 10, 12, 12, PERG),
]
RUNKO_MAC = (100 / 64, 100 / 64, 924 / 64, 924 / 64)  # Applen ruudukko: 824/1024 keskellä
RUNKO_WIN = (1.0, 1.0, 15.0, 15.0)  # Windows: lähes koko ruutu
KULMA_SUHDE = 185 / 824  # kulmasäde suhteessa rungon leveyteen (macOS-muoto)

MAC_KOOT = [16, 32, 128, 256, 512]  # iconset: kukin @1x ja @2x
WIN_KOOT = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def piirra(koko: int, runko: tuple[float, float, float, float]) -> QImage:
    """Kuvake koossa `koko`; kaikki suorat reunat kokonaisiin pikseleihin."""
    u = koko / 16

    def px(arvo: float) -> int:
        return math.floor(arvo * u + 0.5)

    kuva = QImage(koko, koko, QImage.Format.Format_ARGB32_Premultiplied)
    kuva.fill(Qt.GlobalColor.transparent)
    p = QPainter(kuva)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    x0, y0, x1, y1 = (px(v) for v in runko)
    sade = KULMA_SUHDE * (x1 - x0)
    polku = QPainterPath()
    polku.addRoundedRect(QRectF(x0, y0, x1 - x0, y1 - y0), sade, sade)
    p.fillPath(polku, QColor(BURG))
    p.setClipPath(polku)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # suorakulmiot pikseleihin
    for rx0, ry0, rx1, ry1, vari in RIVIT:
        # Leveys ja korkeus pyöristetään erikseen, jotta kaikki rivit ovat yhtä paksuja
        # myös murtolukuskaalassa (20, 24 ja 40 px); muuten reunat pyöristyisivät eri suuntiin.
        p.fillRect(px(rx0), px(ry0), px(rx1 - rx0), px(ry1 - ry0), QColor(vari))
    p.end()
    return kuva


def pilliksi(kuva: QImage) -> Image.Image:
    rgba = kuva.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes(
        "RGBA",
        (rgba.width(), rgba.height()),
        bytes(rgba.constBits()),
        "raw",
        "RGBA",
        rgba.bytesPerLine(),
    )


def tee_png() -> None:
    polku = PACKAGING / "icon.png"
    piirra(1024, RUNKO_MAC).save(str(polku))
    print(f"kirjoitettu {polku.name}")


def tee_ico() -> None:
    kuvat = [pilliksi(piirra(k, RUNKO_WIN)) for k in WIN_KOOT]
    polku = PACKAGING / "icon.ico"
    # append_images: jokainen koko omana piirroksenaan, ei Pillow'n pienennystä
    kuvat[-1].save(polku, format="ICO", sizes=[(k, k) for k in WIN_KOOT], append_images=kuvat[:-1])
    print(f"kirjoitettu {polku.name} ({', '.join(map(str, WIN_KOOT))} px)")


def tee_icns() -> None:
    iconutil = shutil.which("iconutil")
    if sys.platform != "darwin" or iconutil is None:
        print("icon.icns ohitettu: iconutil löytyy vain macOS:stä")
        return
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for k in MAC_KOOT:
            piirra(k, RUNKO_MAC).save(str(iconset / f"icon_{k}x{k}.png"))
            piirra(2 * k, RUNKO_MAC).save(str(iconset / f"icon_{k}x{k}@2x.png"))
        polku = PACKAGING / "icon.icns"
        subprocess.run([iconutil, "-c", "icns", str(iconset), "-o", str(polku)], check=True)
    print(f"kirjoitettu {polku.name}")


def main() -> None:
    sovellus = QGuiApplication.instance() or QGuiApplication([])
    tee_png()
    tee_ico()
    tee_icns()
    del sovellus


if __name__ == "__main__":
    main()
