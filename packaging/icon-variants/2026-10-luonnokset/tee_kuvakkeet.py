"""Opintosuunnitelman muokkaaja: kuvakeluonnokset D–G (lokakuu 2026).

Aja repon juuresta:
    .venv/bin/python -I packaging/icon-variants/2026-10-luonnokset/tee_kuvakkeet.py

Tuottaa tähän kansioon:
    D-*.png … G-*.png      1024 px kuvakkeet (läpinäkyvä tausta rungon ulkopuolella)
    vertailu.png           D–G ja nykyinen A koossa 256/64/32/16 vaalealla ja tummalla
    pikselitarkistus.png   16, 32 ja 48 px pikselit suurennettuina (tarkistusta varten)

Suunnitteluperiaate: kaikki muodot piirretään 16 × 16 -ruudukkoon (1 yksikkö = 64 px
1024 px:n pohjalla = 1 px 16 px:n kuvakkeessa = 2 px 32 px:n kuvakkeessa). Kun reunat
osuvat kokonaisiin yksiköihin, ne pysyvät terävinä myös pienimmissä koissa. Ohuin sisältömuoto
on 1 yksikkö (1/16 kuvakkeesta), eli kaksi kertaa vaadittu vähimmäispaksuus (1/32). Ainoa
poikkeus on G:n reunarengas: 0,5 yksikköä = tasan 1/32, ja se vain rajaa rungon vaalealla
taustalla.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
)

KANSIO = Path(__file__).resolve().parent
REPO = KANSIO.parents[2]
FONTIT = REPO / "src" / "opiskelusuunnitelmoittaja" / "gui" / "fonts"
NYKYINEN = REPO / "packaging" / "icon.png"  # vain luetaan

# BC Helsinki -tokenit (gui/theme.py)
PERG = "#F4ECDD"  # pergamentti
PERG2 = "#EADFC9"  # pergamentti-2
MUSTA = "#1F1813"  # lämmin musta
BURG = "#69013B"  # burgundi
SYVA = "#4A0029"  # syvä burgundi
KULTA = "#9C7A3A"  # kulta

KOKO = 1024
U = 64  # ruudukon yksikkö (1024 / 16)
RUNKO = QRectF(100, 100, 824, 824)  # Applen ruudukko: 824 px runko keskellä
KULMA = 185.0


# ---------------------------------------------------------------- apufunktiot


def runkopolku() -> QPainterPath:
    polku = QPainterPath()
    polku.addRoundedRect(RUNKO, KULMA, KULMA)
    return polku


def palkki(p: QPainter, x0: float, y0: float, x1: float, y1: float, vari: str) -> None:
    """Suorakulmio ruudukon yksiköissä (kulmat terävinä, kuten design systemissä)."""
    p.fillRect(QRectF(x0 * U, y0 * U, (x1 - x0) * U, (y1 - y0) * U), QColor(vari))


def monikulmio(p: QPainter, pisteet: list[tuple[float, float]], vari: str) -> None:
    polku = QPainterPath()
    polku.moveTo(QPointF(pisteet[0][0] * U, pisteet[0][1] * U))
    for x, y in pisteet[1:]:
        polku.lineTo(QPointF(x * U, y * U))
    polku.closeSubpath()
    p.fillPath(polku, QColor(vari))


def uusi_kuva(koko: int = KOKO) -> QImage:
    kuva = QImage(koko, koko, QImage.Format.Format_ARGB32_Premultiplied)
    kuva.fill(Qt.GlobalColor.transparent)
    return kuva


def piirra_kuvake(piirto, pohja: str, reuna: str | None = None) -> QImage:
    """Piirtää rungon ja sisällön. `piirto(p)` saa maalarin, joka on leikattu runkoon."""
    kuva = uusi_kuva()
    p = QPainter(kuva)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    polku = runkopolku()
    p.fillPath(polku, QColor(pohja))
    p.save()
    p.setClipPath(polku)
    piirto(p)
    p.restore()
    if reuna:
        # Rungon sisäreuna: rengas, joka erottaa vaalean rungon vaaleasta taustasta.
        sisa = QPainterPath()
        leveys = 0.5 * U  # 32 px = 1/32 kuvakkeesta (vähimmäispaksuus)
        sisa.addRoundedRect(
            RUNKO.adjusted(leveys, leveys, -leveys, -leveys), KULMA - leveys, KULMA - leveys
        )
        p.fillPath(polku.subtracted(sisa), QColor(reuna))
    p.end()
    return kuva


# ---------------------------------------------------------------- konseptit


def konsepti_d(p: QPainter) -> None:
    """D · Raahattava rivi: taulukon rivit, joista keskimmäinen on irrotettu siirtoon."""
    # Kaksi saraketta (järjestysnumero | sisältö) erottaa taulukon ≡-valikkokuvakkeesta.
    for y in (4, 10):
        palkki(p, 3, y, 5, y + 2, PERG)
        palkki(p, 6, y, 12, y + 2, PERG)
    # Siirrettävä rivi kullalla, yhden yksikön verran oikealle.
    palkki(p, 4, 7, 6, 9, KULTA)
    palkki(p, 7, 7, 13, 9, KULTA)


def konsepti_e(p: QPainter) -> None:
    """E · Rivi lomakkeelle: lomakearkki, johon kultainen rivi on juuri liukumassa."""
    monikulmio(p, [(5, 3), (11, 3), (13, 5), (13, 13), (5, 13)], PERG)  # arkki
    monikulmio(p, [(11, 3), (11, 5), (13, 5)], PERG2)  # taitettu kulma
    palkki(p, 6, 6, 12, 7, BURG)  # jo täytetyt kentät
    palkki(p, 6, 8, 12, 9, BURG)
    palkki(p, 3, 10, 11, 12, KULTA)  # rivi tulossa arkin reunan yli


def konsepti_f(p: QPainter) -> None:
    """F · Aikajana: opintojen osat porrastettuina palkkeina jaksosarakkeiden päällä."""
    for x in (5, 9):  # jaksot (periodit) vuorottelevina sarakkeina
        palkki(p, x, 0, x + 2, 16, SYVA)
    palkki(p, 3, 4, 8, 6, PERG)
    palkki(p, 5, 7, 11, 9, PERG)
    palkki(p, 8, 10, 13, 12, KULTA)


def konsepti_g(p: QPainter) -> None:
    """G · Rivi eteenpäin: pergamentilla taulukon rivit, joista keskimmäinen lähtee nuolena."""
    palkki(p, 3, 4, 8, 6, BURG)
    palkki(p, 3, 10, 8, 12, BURG)
    palkki(p, 3, 7, 9, 9, KULTA)  # nuolen varsi = siirtyvä rivi
    monikulmio(p, [(9, 5), (13, 8), (9, 11)], KULTA)  # kärki, 1 yksikön rako riveihin


KONSEPTIT = [
    ("D", "raahattava-rivi", "Raahattava rivi", konsepti_d, BURG, None),
    ("E", "rivi-lomakkeelle", "Rivi lomakkeelle", konsepti_e, SYVA, None),
    ("F", "aikajana", "Aikajana", konsepti_f, BURG, None),
    ("G", "rivi-eteenpain", "Rivi eteenpäin (pergamentti)", konsepti_g, PERG, BURG),
]


# ---------------------------------------------------------------- muunnokset


def qt_pilliksi(kuva: QImage) -> Image.Image:
    rgba = kuva.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes(
        "RGBA",
        (rgba.width(), rgba.height()),
        bytes(rgba.constBits()),
        "raw",
        "RGBA",
        rgba.bytesPerLine(),
    )


def pilli_qt(kuva: Image.Image) -> QImage:
    data = kuva.convert("RGBA").tobytes()
    q = QImage(data, kuva.width, kuva.height, kuva.width * 4, QImage.Format.Format_RGBA8888)
    return q.copy()  # irrota Python-puskurista


def pienenna(kuva: Image.Image, koko: int) -> Image.Image:
    """Sama menetelmä kuin Pillowin .ico-tallennuksessa (Lanczos, esikerrottu alfa)."""
    return kuva.resize((koko, koko), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------- vertailukuvat

KOOT = [256, 64, 32, 16]
VAALEA = "#ECECEC"
TUMMA = "#1E1E1E"


def lataa_fontit() -> None:
    for ttf in sorted(FONTIT.glob("*.ttf")):
        QFontDatabase.addApplicationFontFromData(ttf.read_bytes())


def fontti(koko: int, paino: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont("Public Sans")
    f.setPixelSize(koko)
    f.setWeight(paino)
    return f


def tee_vertailu(rivit: list[tuple[str, str, Image.Image]]) -> QImage:
    vasen = 300
    paneeli_l = 48 + sum(KOOT) + 48 * (len(KOOT) - 1) + 48
    rivi_k = 256 + 96
    ylä = 120
    leveys = vasen + paneeli_l * 2 + 24 + 40
    korkeus = ylä + rivi_k * len(rivit) + 24 * (len(rivit) - 1) + 40
    kuva = QImage(leveys, korkeus, QImage.Format.Format_ARGB32_Premultiplied)
    kuva.fill(QColor("#FAF7F2"))
    p = QPainter(kuva)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.setPen(QColor(MUSTA))
    p.setFont(fontti(30, QFont.Weight.DemiBold))
    p.drawText(QPointF(40, 56), "Opintosuunnitelman muokkaaja · kuvakeluonnokset D–G")
    p.setFont(fontti(18))
    p.setPen(QColor("#4A3E36"))
    p.drawText(
        QPointF(40, 90),
        "Todellinen pikselikoko 256 · 64 · 32 · 16 px, pienennetty 1024 px:n lähteestä "
        "(Lanczos). Vasemmalla vaalea #ECECEC, oikealla tumma #1E1E1E.",
    )
    for i, (kirjain, nimi, lahde) in enumerate(rivit):
        y0 = ylä + i * (rivi_k + 24)
        p.setPen(QColor(MUSTA))
        p.setFont(fontti(44, QFont.Weight.DemiBold))
        p.drawText(QPointF(40, y0 + 150), kirjain)
        p.setFont(fontti(20))
        p.drawText(QRectF(40, y0 + 168, vasen - 60, 80), Qt.TextFlag.TextWordWrap, nimi)
        for j, tausta in enumerate((VAALEA, TUMMA)):
            x0 = vasen + j * (paneeli_l + 24)
            p.fillRect(QRectF(x0, y0, paneeli_l, rivi_k), QColor(tausta))
            x = x0 + 48
            for koko in KOOT:
                pieni = pilli_qt(pienenna(lahde, koko))
                ky = y0 + 32 + (256 - koko) / 2
                p.drawImage(QPointF(x, ky), pieni)
                p.setPen(QColor("#8A8079" if tausta == VAALEA else "#8F8780"))
                p.setFont(fontti(15))
                p.drawText(
                    QRectF(x - 20, y0 + rivi_k - 44, koko + 40, 24),
                    Qt.AlignmentFlag.AlignHCenter,
                    f"{koko}",
                )
                x += koko + 48
    p.end()
    return kuva


def tee_suurennos(rivit: list[tuple[str, str, Image.Image]]) -> QImage:
    """16, 32 ja 48 px lähikuvana (lähimmän naapurin suurennus 192 px:iin) kummallakin taustalla."""
    koot = (16, 32, 48)
    ruutu = 192
    vali = 12
    ryhmavali = 36
    vasen = 110
    ylä = 96
    leveys = vasen + len(koot) * (2 * ruutu + vali + ryhmavali) + 4
    korkeus = ylä + len(rivit) * (ruutu + 28) + 12
    kuva = QImage(leveys, korkeus, QImage.Format.Format_ARGB32_Premultiplied)
    kuva.fill(QColor("#FAF7F2"))
    p = QPainter(kuva)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.setPen(QColor(MUSTA))
    p.setFont(fontti(24, QFont.Weight.DemiBold))
    p.drawText(QPointF(40, 42), "Pikselitarkistus · 16, 32 ja 48 px suurennettuina")
    p.setFont(fontti(16))
    p.setPen(QColor("#4A3E36"))
    x = vasen
    for koko in koot:
        p.drawText(QPointF(x, 78), f"{koko} px · vaalea | tumma")
        x += 2 * ruutu + vali + ryhmavali
    for i, (kirjain, _nimi, lahde) in enumerate(rivit):
        y = ylä + i * (ruutu + 28)
        p.setPen(QColor(MUSTA))
        p.setFont(fontti(44, QFont.Weight.DemiBold))
        p.drawText(QPointF(40, y + ruutu / 2 + 16), kirjain)
        x = vasen
        for koko in koot:
            pieni = pienenna(lahde, koko)
            for tausta in (VAALEA, TUMMA):
                pohja = Image.new("RGBA", (koko, koko), tausta)
                pohja.alpha_composite(pieni)
                iso = pohja.resize((ruutu, ruutu), Image.Resampling.NEAREST)
                p.drawImage(QPointF(x, y), pilli_qt(iso))
                x += ruutu + vali
            x += ryhmavali - vali
    p.end()
    return kuva


# ---------------------------------------------------------------- pääohjelma


def main() -> None:
    sovellus = QGuiApplication.instance() or QGuiApplication([])
    lataa_fontit()
    rivit: list[tuple[str, str, Image.Image]] = []
    for kirjain, tunnus, nimi, piirto, pohja, reuna in KONSEPTIT:
        kuva = piirra_kuvake(piirto, pohja, reuna)
        polku = KANSIO / f"{kirjain}-{tunnus}.png"
        kuva.save(str(polku))
        rivit.append((kirjain, nimi, qt_pilliksi(kuva)))
        print(f"kirjoitettu {polku.relative_to(REPO)}")
    rivit.append(("A", "Nykyinen (vertailu)", Image.open(NYKYINEN).convert("RGBA")))
    tee_vertailu(rivit).save(str(KANSIO / "vertailu.png"))
    tee_suurennos(rivit).save(str(KANSIO / "pikselitarkistus.png"))
    print("kirjoitettu vertailu.png ja pikselitarkistus.png")
    del sovellus


if __name__ == "__main__":
    main()
