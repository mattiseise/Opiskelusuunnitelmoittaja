@echo off
rem Komentorivi: Suunnitelmoittaja-CLI.cmd chrome | sheets | fill 1,3 | fill --dry-run | fill 1 --korvaa
set "PATH=D:\programming\uv;%PATH%"
set "UV_CACHE_DIR=D:\programming\uv-cache"
set "UV_PYTHON_INSTALL_DIR=D:\programming\uv-python"
cd /d "%~dp0"
"D:\programming\uv\uv.exe" run --project "%~dp0." suunnitelmoittaja %*
