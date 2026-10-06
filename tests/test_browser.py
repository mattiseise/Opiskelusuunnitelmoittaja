"""Kytkeytyminen käyttäjän Chromeen: välilehti, jota Playwright ei saa haltuunsa.

Kun Chrome on esiladannut sivun ja välilehti siirtyy siihen, välilehden pääkehyksen
tunniste vaihtuu. Playwright ei silloin saa välilehteä haltuunsa: ``page.url`` jää tyhjäksi
ja jokainen kysely siihen odottaa ikuisesti (GUI jäätyi täyttöä aloitettaessa).
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest
from playwright.sync_api import sync_playwright

from opiskelusuunnitelmoittaja.browser import connect, find_form_page, is_chrome_listening
from opiskelusuunnitelmoittaja.config import BrowserConfig

FIXTURES = Path(__file__).parent / "fixtures"
FORM = 'table:has(th:has-text("Osaamistavoite")) tbody'
START_PAGE = b"""<!doctype html><title>Wilma</title>
<script type="speculationrules">
{"prerender": [{"source": "list", "urls": ["/wilma-lomake.html"]}]}
</script>
<a id="lomake" href="/wilma-lomake.html">Opintosuunnitelma</a>"""


class _Handler(SimpleHTTPRequestHandler):
    requested: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        self.requested.append(self.path)
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(START_PAGE)
            return
        super().do_GET()

    def log_message(self, format: str, *args: Any) -> None:
        pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _chrome_executable() -> str:
    override = os.environ.get("SUUNNITELMOITTAJA_CHROMIUM")
    if override:
        return override
    with sync_playwright() as pw:
        return pw.chromium.executable_path


def _wait(condition: Any, what: str, timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline:
            pytest.skip(f"selain ei {what} {timeout_s:.0f} sekunnissa")
        time.sleep(0.1)


def _in_thread(fn: Any) -> Any:
    """Aja omassa säikeessään: pytest-playwrightin Sync API voi olla jo käynnissä tässä."""
    result: dict[str, Any] = {}

    def run() -> None:
        try:
            result["value"] = fn()
        except BaseException as exc:  # välitetään testisäikeeseen (myös pytest.skip)
            result["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(60)
    assert not thread.is_alive(), "Playwright jäi jumiin"
    if "error" in result:
        raise result["error"]
    return result.get("value")


@pytest.fixture
def prerendered_tab(tmp_path: Path):
    """Chrome, jonka ainoa välilehti siirtyi esiladatulle Wilma-lomakkeelle."""
    executable = _in_thread(_chrome_executable)
    if not Path(executable).exists():
        pytest.skip(f"Chromea ei löydy: {executable}")
    _Handler.requested = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler, directory=str(FIXTURES)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cfg = BrowserConfig(remote_debugging_port=_free_port(), user_data_dir=str(tmp_path / "p"))
    chrome = subprocess.Popen(
        [
            executable,
            "--headless=new",
            "--no-sandbox",  # CI:n Ubuntu estää Chromen hiekkalaatikon; vain paikallinen testisivu
            "--no-first-run",
            "--no-default-browser-check",
            f"--remote-debugging-port={cfg.remote_debugging_port}",
            f"--user-data-dir={cfg.user_data_dir}",
            f"http://127.0.0.1:{server.server_port}/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait(lambda: is_chrome_listening(cfg), "käynnistynyt")
        _wait(lambda: "/wilma-lomake.html" in _Handler.requested, "esiladannut lomaketta")
        time.sleep(1)  # esilataus valmiiksi ennen siirtymää

        def follow_link() -> None:
            with connect(cfg) as browser:
                page = browser.contexts[0].pages[0]
                page.evaluate("document.getElementById('lomake').click()")
                page.wait_for_timeout(2000)

        _in_thread(follow_link)
        yield cfg
    finally:
        chrome.terminate()
        chrome.wait(10)
        server.shutdown()


def test_find_form_page_reopens_tab_playwright_cannot_control(
    prerendered_tab: BrowserConfig,
) -> None:
    cfg = prerendered_tab

    def find() -> tuple[str, int, list[str]]:
        with connect(cfg) as browser:
            pages = browser.contexts[0].pages
            if any(p.url for p in pages):
                pytest.skip("selain ei vaihtanut esiladattua sivua välilehteen")
            page = find_form_page(browser, cfg, FORM)
            return page.url, page.locator(FORM).count(), [p.url for p in browser.contexts[0].pages]

    url, forms, open_urls = _in_thread(find)
    assert url.endswith("/wilma-lomake.html")
    assert forms == 1
    assert open_urls == [url]  # vanha, käyttökelvoton välilehti suljettiin

    def find_again() -> str:  # uusi välilehti toimii myös seuraavalla yhteydellä
        with connect(cfg) as browser:
            return find_form_page(browser, cfg, FORM).url

    assert _in_thread(find_again) == url
