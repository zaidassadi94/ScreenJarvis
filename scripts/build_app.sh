#!/usr/bin/env bash
#
# Build ScreenJarvis.app (and a distributable DMG) on macOS.
#
#   ./scripts/build_app.sh
#
# Optional code signing + notarization (Developer ID account required):
#   SJ_SIGN_IDENTITY="Developer ID Application: You (TEAMID)" \
#   SJ_NOTARY_PROFILE="sj-notary" \
#     ./scripts/build_app.sh
# See packaging/BUILD.md for the full signing / notarization walkthrough.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "$(uname)" != "Darwin" ]]; then
  echo "build_app.sh only runs on macOS (py2app / iconutil / hdiutil are macOS tools)." >&2
  exit 1
fi

echo "==> icon"
python3 packaging/icon/make_icon.py
iconutil -c icns packaging/icon/ScreenJarvis.iconset -o packaging/icon/ScreenJarvis.icns

echo "==> clean"
rm -rf build dist .venv-app

echo "==> build env"
python3 -m venv .venv-app
# shellcheck disable=SC1091
source .venv-app/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e . py2app

echo "==> py2app"
python packaging/setup_app.py py2app

APP="dist/ScreenJarvis.app"

if [[ -n "${SJ_SIGN_IDENTITY:-}" ]]; then
  echo "==> codesign"
  codesign --deep --force --options runtime --timestamp \
    --sign "$SJ_SIGN_IDENTITY" "$APP"
  codesign --verify --strict --verbose=2 "$APP"
fi

echo "==> dmg"
hdiutil create -volname ScreenJarvis -srcfolder "$APP" \
  -ov -format UDZO dist/ScreenJarvis.dmg

if [[ -n "${SJ_NOTARY_PROFILE:-}" ]]; then
  echo "==> notarize"
  xcrun notarytool submit dist/ScreenJarvis.dmg \
    --keychain-profile "$SJ_NOTARY_PROFILE" --wait
  xcrun stapler staple dist/ScreenJarvis.dmg
  xcrun stapler staple "$APP"
fi

echo
echo "done:"
echo "  $APP"
echo "  dist/ScreenJarvis.dmg"
