#!/usr/bin/env bash
# Tekee kehityskäynnistimen macOS:lle: ~/Applications/Opiskelusuunnitelmoittaja (dev).app
# Käynnistin ajaa `uv run suunnitelmoittaja-gui` tästä repokansiosta, joten koodimuutokset
# näkyvät heti ilman PyInstaller-buildia. Ikoni tehdään packaging/icon.png:stä.
#
#   scripts/make-launcher.sh            → ~/Applications/Opiskelusuunnitelmoittaja (dev).app
#   scripts/make-launcher.sh --dock     → sama + lisää Dockiin
#
# Varsinainen jaettava sovellus rakennetaan scripts/build.sh:lla (PyInstaller, ei vaadi uv:ta).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
NAME="Opiskelusuunnitelmoittaja (dev)"
APP="$HOME/Applications/$NAME.app"
UV_BIN="$(command -v uv || true)"
[[ -n "$UV_BIN" ]] || { echo "uv ei löydy PATHista. Asenna: brew install uv"; exit 1; }
[[ "$(uname -s)" == "Darwin" ]] || { echo "Tämä skripti on macOS:lle. Linuxissa käytä scripts/build.sh."; exit 1; }

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/MacOS/launch" <<LAUNCH
#!/usr/bin/env bash
# Käynnistää GUI:n repokansiosta. Loki: ~/Library/Logs/Opiskelusuunnitelmoittaja-dev.log
export PATH="$(dirname "$UV_BIN"):/opt/homebrew/bin:/usr/local/bin:\$PATH"
cd "$REPO"
exec "$UV_BIN" run --project "$REPO" suunnitelmoittaja-gui >> "\$HOME/Library/Logs/Opiskelusuunnitelmoittaja-dev.log" 2>&1
LAUNCH
chmod +x "$APP/Contents/MacOS/launch"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleIdentifier</key><string>fi.seise.opiskelusuunnitelmoittaja.dev</string>
  <key>CFBundleVersion</key><string>dev</string>
  <key>CFBundleShortVersionString</key><string>dev</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

# PNG → ICNS (sips + iconutil ovat macOS:n mukana)
ICONSET="$(mktemp -d)/icon.iconset"
mkdir -p "$ICONSET"
for s in 16 32 64 128 256 512; do
  sips -z $s $s "$REPO/packaging/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s*2)); sips -z $d $d "$REPO/packaging/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/icon.icns"
rm -rf "$(dirname "$ICONSET")"
touch "$APP"  # Finder päivittää ikonin

echo "✔ $APP"
if [[ "${1:-}" == "--dock" ]]; then
  defaults write com.apple.dock persistent-apps -array-add \
    "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>$APP</string><key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>"
  killall Dock
  echo "✔ Lisätty Dockiin"
fi
echo "Avaa Launchpadista tai Spotlightista: \"$NAME\". Ensimmäinen käynnistys kestää hetken (uv sync)."
