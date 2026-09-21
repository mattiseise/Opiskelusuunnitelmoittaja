@echo off
rem Käynnistää Opintosuunnitelman täyttäjän käyttöliittymän kehitysversiona tästä repokansiosta.
rem uv on asennettu D:\programming\uv (ei PATHissa), välimuisti D:\programming\uv-cache.
rem uv lisätään PATHiin, jotta sovelluksen Päivitä-nappi voi ajaa "uv sync" git pullin jälkeen.
set "PATH=D:\programming\uv;%PATH%"
set "UV_CACHE_DIR=D:\programming\uv-cache"
set "UV_PYTHON_INSTALL_DIR=D:\programming\uv-python"
cd /d "%~dp0"
start "" "D:\programming\uv\uvw.exe" run --project "%~dp0." suunnitelmoittaja-gui
