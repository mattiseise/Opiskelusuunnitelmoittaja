#!/usr/bin/env bash
# Rakentaa standalone-sovelluksen macOS:lle (tai Linuxille) PyInstallerilla.
#   scripts/build.sh            → dist/Opintosuunnitelman muokkaaja.app + dist/OpintosuunnitelmanTayttaja-<versio>-macos-<arch>.dmg
#   scripts/build.sh --no-dmg   → vain .app
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(uv run python -c "import opiskelusuunnitelmoittaja as m; print(m.__version__)")
ARCH=$(uname -m)
OS=$(uname -s)

echo "▶ Riippuvuudet"
uv sync --extra gui --quiet

echo "▶ Testit (nopeat)"
uv run pytest -q -x --ignore=tests/test_filler.py --ignore=tests/test_gui.py

echo "▶ PyInstaller"
rm -rf build dist
uv run pyinstaller packaging/OpintosuunnitelmanTayttaja.spec --noconfirm --log-level WARN

if [[ "$OS" == "Darwin" ]]; then
  APP="dist/Opintosuunnitelman muokkaaja.app"
  # Playwrightin node-binäärin pitää olla ajettava
  chmod +x "$APP/Contents/Frameworks/playwright/driver/node" 2>/dev/null || \
  chmod +x "$APP/Contents/Resources/playwright/driver/node" 2>/dev/null || true
  # Ad-hoc-allekirjoitus, jotta Gatekeeper ei hylkää pakettia "damaged"-virheellä
  codesign --force --deep --sign - "$APP"
  echo "▶ Savutesti"
  "$APP/Contents/MacOS/OpintosuunnitelmanTayttaja" --cli --version

  if [[ "${1:-}" != "--no-dmg" ]]; then
    DMG="dist/OpintosuunnitelmanTayttaja-${VERSION}-macos-${ARCH}.dmg"
    echo "▶ DMG: $DMG"
    STAGE=$(mktemp -d)
    cp -R "$APP" "$STAGE/"
    ln -s /Applications "$STAGE/Applications"
    hdiutil create -volname "Opintosuunnitelman muokkaaja" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
    rm -rf "$STAGE"
    echo "✔ $DMG"
  fi
  echo "✔ $APP"
else
  OUT="dist/OpintosuunnitelmanTayttaja-${VERSION}-${OS,,}-${ARCH}.tar.gz"
  tar -C dist -czf "$OUT" OpintosuunnitelmanTayttaja
  echo "✔ $OUT"
fi
