"""Päivityksen tarkistus ja haku paikallista git-repoa vastaan (ei verkkoa)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from opiskelusuunnitelmoittaja import update

pytestmark = pytest.mark.skipif(not update.git_available(), reason="git puuttuu")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def _commit(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(
        repo,
        "-c",
        "user.name=Testi",
        "-c",
        "user.email=testi@example.com",
        "commit",
        "-q",
        "-m",
        f"lisää {name}",
    )


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path]:
    """(paikallinen klooni, toinen klooni joka pushaa uutta) yhteisen bare-etärepon kautta."""
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "-q", str(remote), str(seed))
    _git(seed, "checkout", "-q", "-b", "main")
    (seed / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    _commit(seed, "README.md", "alku")
    _git(seed, "push", "-q", "-u", "origin", "main")
    local = tmp_path / "local"
    _git(tmp_path, "clone", "-q", "-b", "main", str(remote), str(local))
    return local, seed


def test_missing_upstream_gives_clear_error(tmp_path: Path) -> None:
    repo = tmp_path / "irrallinen"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    _commit(repo, "README.md", "alku")
    with pytest.raises(update.UpdateError, match="etähaaraa"):
        update.check_for_update(repo)


def test_up_to_date(repos: tuple[Path, Path]) -> None:
    local, _seed = repos
    check = update.check_for_update(local)
    assert check.kind == "git"
    assert not check.available
    assert check.summary.startswith("Ajan tasalla")
    assert update.apply_update(local, run_sync=False).startswith("Ei uusia muutoksia")


def test_detects_and_pulls_new_commits(repos: tuple[Path, Path]) -> None:
    local, seed = repos
    _commit(seed, "uusi.txt", "1")
    _commit(seed, "toinen.txt", "2")
    _git(seed, "push", "-q")

    check = update.check_for_update(local)
    assert check.available
    assert "2 uutta committia" in check.latest
    assert "lisää uusi.txt" in check.details and "lisää toinen.txt" in check.details
    assert check.warnings == []

    logged: list[str] = []
    message = update.apply_update(local, log=logged.append, run_sync=False)
    assert message.startswith("Päivitetty ")
    assert "Käynnistä sovellus uudelleen" in message
    assert (local / "toinen.txt").exists()
    assert any("git pull" in m for m in logged)
    assert not update.check_for_update(local).available


def test_warns_about_local_changes_and_fails_on_conflict(repos: tuple[Path, Path]) -> None:
    local, seed = repos
    (local / "README.md").write_text("paikallinen muutos", encoding="utf-8")
    check = update.check_for_update(local)
    assert any("Muokattuja tiedostoja" in w for w in check.warnings)

    _commit(seed, "README.md", "etämuutos")
    _git(seed, "push", "-q")
    with pytest.raises(update.UpdateError, match="git pull epäonnistui"):
        update.apply_update(local, run_sync=False)


def test_version_comparison() -> None:
    assert update.is_newer("2.2.0", "2.1.0")
    assert update.is_newer("v10.0.0", "9.9.9")
    assert not update.is_newer("2.1.0", "2.1.0")
    assert not update.is_newer("2.0.9", "2.1.0")
    assert not update.is_newer("", "2.1.0")


def test_repo_root_points_to_this_checkout() -> None:
    root = update.repo_root()
    if root is None:
        pytest.skip("ei git-kloonia (esim. asennettu paketti)")
    assert (root / "pyproject.toml").exists()
    assert (root / "src" / "opiskelusuunnitelmoittaja").is_dir()
