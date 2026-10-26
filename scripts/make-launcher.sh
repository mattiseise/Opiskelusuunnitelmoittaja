#!/usr/bin/env bash
# Tekee kehityskäynnistimen macOS:lle: ~/Applications/Opintosuunnitelman muokkaaja.app
# Käynnistin ajaa `uv run suunnitelmoittaja-gui` tästä repokansiosta, joten koodimuutokset
# näkyvät heti ilman PyInstaller-buildia. Ikoni on packaging/icon.icns (scripts/make-icons.py).
# Windowsin vastine: scripts/make-launcher.ps1.
#
#   scripts/make-launcher.sh            → ~/Applications/Opintosuunnitelman muokkaaja.app
#   scripts/make-launcher.sh --dock     → sama + lisää Dockiin
#
# Varsinainen jaettava sovellus rakennetaan scripts/build.sh:lla (PyInstaller, ei vaadi uv:ta).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
NAME="Opintosuunnitelman muokkaaja"
APP="$HOME/Applications/$NAME.app"
# Vanhat kehityskäynnistimet pois, jotta Dockiin/Launchpadiin ei jää tuplia
for old in "$HOME/Applications/Opintosuunnitelman täyttäjä (dev).app" \
           "$HOME/Applications/Opintosuunnitelman täyttäjä (Dev).app" \
           "$HOME/Applications/Opintosuunnitelman muokkaaja (dev).app"; do
  [[ -d "$old" ]] && rm -rf "$old" && echo "poistettu vanha käynnistin: $old"
done
UV_BIN="$(command -v uv || true)"
[[ -n "$UV_BIN" ]] || { echo "uv ei löydy PATHista. Asenna: brew install uv"; exit 1; }
[[ "$(uname -s)" == "Darwin" ]] || { echo "Tämä skripti on macOS:lle. Linuxissa käytä scripts/build.sh."; exit 1; }

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/MacOS/launch" <<LAUNCH
#!/usr/bin/env bash
# Käynnistää GUI:n repokansiosta. Loki: ~/Library/Logs/OpintosuunnitelmanMuokkaaja.log
export PATH="$(dirname "$UV_BIN"):/opt/homebrew/bin:/usr/local/bin:\$PATH"
cd "$REPO"
exec "$UV_BIN" run --project "$REPO" suunnitelmoittaja-gui >> "\$HOME/Library/Logs/OpintosuunnitelmanMuokkaaja.log" 2>&1
LAUNCH
chmod +x "$APP/Contents/MacOS/launch"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleIdentifier</key><string>fi.seise.opintosuunnitelmanmuokkaaja.local</string>
  <key>CFBundleVersion</key><string>dev</string>
  <key>CFBundleShortVersionString</key><string>dev</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

# Valmis ICNS (scripts/make-icons.py), jossa pienet koot on piirretty erikseen teräviksi
cp "$REPO/packaging/icon.icns" "$APP/Contents/Resources/icon.icns"
touch "$APP"  # Finder päivittää ikonin

echo "✔ $APP"
if [[ "${1:-}" == "--dock" ]]; then
  defaults write com.apple.dock persistent-apps -array-add \
    "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>$APP</string><key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>"
  killall Dock
  echo "✔ Lisätty Dockiin"
fi
echo "Avaa Launchpadista tai Spotlightista: \"$NAME\". Ensimmäinen käynnistys kestää hetken (uv sync)."
