# Rakentaa standalone-sovelluksen Windowsille PyInstallerilla.
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1
# Tulos: dist\OpintosuunnitelmanTayttaja\ ja dist\OpintosuunnitelmanTayttaja-<versio>-windows-x64.zip
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$version = uv run python -c "import opiskelusuunnitelmoittaja as m; print(m.__version__)"

Write-Host "> Riippuvuudet"
uv sync --extra gui --quiet

Write-Host "> Testit (nopeat)"
uv run pytest -q -x --ignore=tests/test_filler.py --ignore=tests/test_gui.py

Write-Host "> PyInstaller"
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist)  { Remove-Item dist  -Recurse -Force }
uv run pyinstaller packaging/OpintosuunnitelmanTayttaja.spec --noconfirm --log-level WARN

Write-Host "> Savutesti"
& "dist\OpintosuunnitelmanTayttaja\OpintosuunnitelmanTayttaja.exe" --cli --version

$zip = "dist\OpintosuunnitelmanTayttaja-$version-windows-x64.zip"
Compress-Archive -Path "dist\OpintosuunnitelmanTayttaja" -DestinationPath $zip -Force
Write-Host "OK $zip"
