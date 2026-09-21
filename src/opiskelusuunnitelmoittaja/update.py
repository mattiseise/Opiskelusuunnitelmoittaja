"""Päivitys: kehitysversio gitistä, paketoitu sovellus GitHubin Releases-sivulta.

Kehitysversio (``uv run suunnitelmoittaja-gui`` repokansiosta): ``git fetch`` kertoo, onko
etähaarassa uusia committeja; ``git pull --ff-only`` hakee ne ja ``uv sync --extra gui``
päivittää riippuvuudet, jos uv löytyy. Sen jälkeen sovellus pitää käynnistää uudelleen.

Paketoitu sovellus (PyInstaller): kysytään GitHubin API:sta uusin release ja verrataan
versionumeroon. Päivitys tehdään lataamalla uusi paketti Releases-sivulta.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .paths import is_frozen

GITHUB_REPO = "mattiseise/Opiskelusuunnitelmoittaja"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

Logger = Callable[[str], None]


class UpdateError(Exception):
    """Päivityksen tarkistus tai haku epäonnistui."""


@dataclass(slots=True)
class UpdateCheck:
    kind: str  # "git" (kehitysversio) tai "release" (paketti)
    current: str  # nykyinen versio tai commit
    latest: str  # uusin saatavilla oleva
    available: bool
    details: str = ""  # commit-lista tai release-kuvaus
    url: str = RELEASES_URL
    root: Path | None = None  # repon juuri, kun kind == "git"
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.kind == "git":
            if self.available:
                return f"Uusia muutoksia gitissä: {self.latest} (nyt {self.current})"
            return f"Ajan tasalla ({self.current})"
        if self.available:
            return f"Uusi versio {self.latest} saatavilla (nyt {self.current})"
        return f"Ajan tasalla (versio {self.current})"


# --- tunnistus ----------------------------------------------------------------


def repo_root() -> Path | None:
    """Repon juuri, jos sovellus ajetaan lähdekoodista git-kloonista; muuten None."""
    if is_frozen():
        return None
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists() and (parent / "pyproject.toml").exists():
            return parent
    return None


def git_available() -> bool:
    return shutil.which("git") is not None


def uv_executable() -> str | None:
    """uv:n polku: ympäristömuuttuja SUUNNITELMOITTAJA_UV, sitten PATH."""
    override = os.environ.get("SUUNNITELMOITTAJA_UV")
    if override and Path(override).exists():
        return override
    return shutil.which("uv")


# --- tarkistus ----------------------------------------------------------------


def check_for_update(root: Path | None = None, *, timeout_s: float = 30.0) -> UpdateCheck:
    root = root if root is not None else repo_root()
    if root is not None:
        return _check_git(root, timeout_s=timeout_s)
    return _check_release(timeout_s=timeout_s)


def _check_git(root: Path, *, timeout_s: float) -> UpdateCheck:
    if not git_available():
        raise UpdateError("git ei löydy PATHista. Asenna Git tai päivitä käsin: git pull")
    try:
        upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").strip()
    except UpdateError as exc:
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        raise UpdateError(
            f"Haaralla '{branch}' ei ole etähaaraa (upstream), joten päivitystä ei voi "
            "tarkistaa. Aseta se: git branch --set-upstream-to=origin/main"
        ) from exc
    _git(root, "fetch", "--quiet", timeout_s=timeout_s)
    current = _git(root, "rev-parse", "--short", "HEAD").strip()
    latest = _git(root, "rev-parse", "--short", "@{u}").strip()
    behind = int(_git(root, "rev-list", "--count", "HEAD..@{u}").strip() or "0")
    ahead = int(_git(root, "rev-list", "--count", "@{u}..HEAD").strip() or "0")
    details = _git(root, "log", "--oneline", "--no-decorate", "HEAD..@{u}").strip()
    warnings: list[str] = []
    if ahead:
        warnings.append(
            f"Paikallisessa haarassa on {ahead} committia, joita ei ole etähaarassa {upstream}."
        )
    dirty = _dirty_tracked_files(root)
    if dirty:
        warnings.append("Muokattuja tiedostoja: " + ", ".join(dirty[:5]))
    return UpdateCheck(
        kind="git",
        current=current,
        latest=f"{latest} ({behind} uutta committia)" if behind else latest,
        available=behind > 0,
        details=details,
        root=root,
        warnings=warnings,
    )


def _check_release(*, timeout_s: float) -> UpdateCheck:
    request = urllib.request.Request(
        RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"OpintosuunnitelmanTayttaja/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise UpdateError(f"Releases-tietoja ei saatu GitHubista: {exc}") from exc
    tag = str(data.get("tag_name") or "")
    latest = tag.lstrip("vV") or "?"
    return UpdateCheck(
        kind="release",
        current=__version__,
        latest=latest,
        available=is_newer(latest, __version__),
        details=str(data.get("body") or "").strip(),
        url=str(data.get("html_url") or RELEASES_URL),
    )


def is_newer(candidate: str, current: str) -> bool:
    """Onko ``candidate`` uudempi versionumero kuin ``current`` (2.1.0 < 2.2.0 < 10.0.0)."""
    return _version_tuple(candidate) > _version_tuple(current)


def _version_tuple(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", text)
    return tuple(int(n) for n in numbers) or (0,)


# --- päivitys -----------------------------------------------------------------


def apply_update(
    root: Path | None = None,
    *,
    log: Logger | None = None,
    run_sync: bool = True,
    timeout_s: float = 300.0,
) -> str:
    """Hae uusin versio gitistä (``git pull --ff-only``) ja synkkaa riippuvuudet.

    Palauttaa lyhyen kuvauksen tehdystä. Nostaa UpdateError, jos pull ei onnistu
    (esim. paikalliset muutokset ovat ristiriidassa).
    """
    say = log or (lambda _m: None)
    root = root if root is not None else repo_root()
    if root is None:
        raise UpdateError(
            "Tämä on paketoitu sovellus: lataa uusi versio Releases-sivulta.\n" + RELEASES_URL
        )
    if not git_available():
        raise UpdateError("git ei löydy PATHista.")
    before = _git(root, "rev-parse", "--short", "HEAD").strip()
    say(f"git pull --ff-only ({root})")
    try:
        output = _git(root, "pull", "--ff-only", timeout_s=timeout_s)
    except UpdateError as exc:
        raise UpdateError(
            "git pull epäonnistui. Paikalliset muutokset voivat olla ristiriidassa; "
            f"tarkista repokansio {root}.\n\n{exc}"
        ) from exc
    say(output.strip() or "(ei tulostetta)")
    after = _git(root, "rev-parse", "--short", "HEAD").strip()
    if before == after:
        return f"Ei uusia muutoksia ({after})."

    lines = [f"Päivitetty {before} → {after}."]
    if run_sync:
        uv = uv_executable()
        if uv:
            say(f"{uv} sync --extra gui")
            try:
                sync_out = _run([uv, "sync", "--extra", "gui"], cwd=root, timeout_s=timeout_s)
                say(sync_out.strip() or "(ei tulostetta)")
                lines.append("Riippuvuudet synkattu (uv sync).")
            except UpdateError as exc:
                lines.append(f"uv sync epäonnistui: {exc}")
        else:
            lines.append(
                "uv ei löydy PATHista; aja tarvittaessa `uv sync --extra gui` repokansiossa."
            )
    lines.append("Käynnistä sovellus uudelleen, jotta muutokset tulevat käyttöön.")
    return "\n".join(lines)


def restart_application(root: Path | None = None) -> None:
    """Käynnistä uusi instanssi sovelluksesta; kutsuja sulkee nykyisen."""
    if is_frozen():
        cmd = [sys.executable, *sys.argv[1:]]
        cwd = None
    else:
        cmd = [sys.executable, "-m", "opiskelusuunnitelmoittaja.gui.app", *sys.argv[1:]]
        cwd = str(root or repo_root() or Path.cwd())
    kwargs: dict[str, object] = {"cwd": cwd, "close_fds": True}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)  # type: ignore[call-overload]


# --- apurit -------------------------------------------------------------------


def _dirty_tracked_files(root: Path) -> list[str]:
    status = _git(root, "status", "--porcelain", "--untracked-files=no")
    return [line[3:].strip() for line in status.splitlines() if line.strip()]


def _git(root: Path, *args: str, timeout_s: float = 60.0) -> str:
    return _run(["git", *args], cwd=root, timeout_s=timeout_s)


def _run(cmd: list[str], *, cwd: Path, timeout_s: float) -> str:
    kwargs: dict[str, object] = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
            **kwargs,  # type: ignore[arg-type]
        )
    except FileNotFoundError as exc:
        raise UpdateError(f"komentoa ei löydy: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise UpdateError(f"{' '.join(cmd)} ei valmistunut {timeout_s:.0f} sekunnissa") from exc
    if result.returncode != 0:
        raise UpdateError(
            f"{' '.join(cmd)} päättyi virheeseen {result.returncode}:\n"
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout
