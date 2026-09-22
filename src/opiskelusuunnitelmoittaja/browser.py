"""Chromen käynnistys etädebuggauksella ja siihen kytkeytyminen Playwrightin CDP-yhteydellä."""

from __future__ import annotations

import logging
import platform
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from .config import BrowserConfig

log = logging.getLogger("suunnitelmoittaja.browser")


class BrowserError(Exception):
    """Chromeen ei saada yhteyttä tai lomakesivua ei löydy."""


def cdp_url(cfg: BrowserConfig) -> str:
    return f"http://127.0.0.1:{cfg.remote_debugging_port}"


def is_chrome_listening(cfg: BrowserConfig, timeout_s: float = 1.0) -> bool:
    """Vastaako Chrome etädebugausportissa?"""
    try:
        with urllib.request.urlopen(f"{cdp_url(cfg)}/json/version", timeout=timeout_s) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def launch_chrome(cfg: BrowserConfig, wait_s: float = 15.0) -> None:
    """Käynnistä Chrome erilliseen profiiliin etädebuggaus päällä ja odota, että portti vastaa.

    Chrome 136+ ei salli etädebuggausta oletusprofiilissa, siksi käytetään omaa
    ``user_data_dir``-hakemistoa. Kirjautumiset säilyvät siinä kertojen välillä.
    """
    if is_chrome_listening(cfg):
        log.info("Chrome kuuntelee jo portissa %d", cfg.remote_debugging_port)
        return

    cfg.resolved_user_data_dir().mkdir(parents=True, exist_ok=True)
    chrome = cfg.resolved_chrome_path()
    if chrome is None:
        raise BrowserError(
            "Google Chromea ei löytynyt. Aseta polku config.json → browser.chrome_path "
            "tai käynnistä Chrome käsin komennolla:\n  " + cfg.launch_command()
        )

    if platform.system() == "Darwin":
        cmd = ["open", "-na", "Google Chrome", "--args", *cfg.launch_args()]
    else:
        cmd = [chrome, *cfg.launch_args()]
    log.info("Käynnistetään Chrome: %s", " ".join(cmd))
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if is_chrome_listening(cfg):
            log.info("Chrome vastaa portissa %d", cfg.remote_debugging_port)
            return
        time.sleep(0.3)
    raise BrowserError(
        f"Chrome ei alkanut kuunnella porttia {cfg.remote_debugging_port} {wait_s:.0f} sekunnissa."
    )


@contextmanager
def connect(cfg: BrowserConfig) -> Iterator[Browser]:
    """Kytkeydy käynnissä olevaan Chromeen. Selainta ei suljeta poistuttaessa."""
    if not is_chrome_listening(cfg):
        raise BrowserError(
            f"Chrome ei vastaa osoitteessa {cdp_url(cfg)}. Käynnistä se ensin:\n"
            f"  suunnitelmoittaja chrome\n"
            f"tai käsin:\n  {cfg.launch_command()}"
        )
    pw: Playwright = sync_playwright().start()
    browser: Browser | None = None
    try:
        browser = pw.chromium.connect_over_cdp(cdp_url(cfg), timeout=cfg.timeout_ms)
        log.info("Yhteys Chromeen muodostettu (%s)", browser.version)
        yield browser
    finally:
        # connect_over_cdp: close() katkaisee vain yhteyden, ei sulje käyttäjän Chromea.
        if browser is not None:
            browser.close()
        pw.stop()


# Vain leivänmurun oma linkki (li > a). Opiskelijakohdassa on myös pudotusvalikko, jossa
# on koko ryhmän opiskelijat linkkeinä (ul.dropdown-menu li a) – ne eivät saa osua.
STUDENT_LINK = ".breadcrumb > li > a[href*='/profiles/students/']"


def student_name(page: Page) -> str:
    """Opiskelijan nimi lomakesivun leivänmurupolusta; tyhjä, jos sitä ei löydy.

    Wilman opintokortin polku on Oma etusivu › Opiskelijat › Koulu › Ryhmä › *Opiskelija* ›
    Opintosuunnitelma. Opiskelijan linkki osoittaa /profiles/students/<id>; listalinkki
    /profiles/students ei osu valitsimeen, koska siitä puuttuu kauttaviiva ja tunnus.
    """
    try:
        links = page.locator(STUDENT_LINK)
        if links.count() == 0:
            return ""
        text = links.first.inner_text(timeout=2000)
        return " ".join(text.replace("\xa0", " ").split())
    except Exception as exc:  # sivu vaihtui kesken tai ei ole Wilma
        log.debug("Opiskelijan nimeä ei saatu: %s", exc)
        return ""


def describe_page(page: Page) -> str:
    """Lyhyt kuvaus vahvistusikkunaan: opiskelijan nimi tai sivun otsikko/osoite."""
    name = student_name(page)
    if name:
        return name
    try:
        return page.title() or page.url
    except Exception:
        return page.url


def find_form_page(browser: Browser, cfg: BrowserConfig, form_selector: str) -> Page:
    """Etsi välilehti, jolla lomake on.

    Ensisijaisesti URL-osuman, toissijaisesti lomake-elementin perusteella.
    """
    pages = [p for ctx in browser.contexts for p in ctx.pages]
    if not pages:
        raise BrowserError("Chromessa ei ole yhtään avointa välilehteä.")

    if cfg.page_url_contains:
        for page in pages:
            if cfg.page_url_contains in page.url:
                log.info("Lomakesivu löytyi URL-osumalla: %s", page.url)
                return page
        raise BrowserError(
            f"Yhtään välilehteä, jonka osoite sisältää '{cfg.page_url_contains}', ei ole auki. "
            f"Avoinna: {[p.url for p in pages]}"
        )

    for page in pages:
        try:
            if page.locator(form_selector).count() > 0:
                log.info("Lomakesivu löytyi lomake-elementin perusteella: %s", page.url)
                return page
        except Exception as exc:  # esim. chrome:// -sivut
            log.debug("Välilehteä %s ei voitu tarkastaa: %s", page.url, exc)
    raise BrowserError(
        "Lomaketta ei löytynyt miltään avoimelta välilehdeltä. Avaa lomakesivu Chromessa "
        f"ja yritä uudelleen. Avoinna: {[p.url for p in pages]}"
    )
