# Building the ScreenJarvis macOS app

This turns the Python package into a double-clickable **ScreenJarvis.app** — no
terminal, no `uv`, and macOS permissions that attach to *ScreenJarvis* itself
instead of to Terminal or a bare "Python". Two artifacts come out:
`dist/ScreenJarvis.app` and `dist/ScreenJarvis.dmg`.

Everything here runs **on a Mac** (py2app, `iconutil`, `hdiutil`, `codesign`,
and `notarytool` are macOS tools). The recorder/compiler code itself is
unchanged — this is packaging only.

## Quick build (unsigned, for yourself)

```sh
git clone https://github.com/zaidassadi94/ScreenJarvis
cd ScreenJarvis
./scripts/build_app.sh
```

That script:
1. renders the icon (`packaging/icon/make_icon.py`) and makes `ScreenJarvis.icns`,
2. creates an isolated build venv and installs the package + `py2app`,
3. runs `python packaging/setup_app.py py2app` → `dist/ScreenJarvis.app`,
4. wraps it in `dist/ScreenJarvis.dmg`.

Then drag **ScreenJarvis.app** to `/Applications` and launch it. A 🎙 appears in
the menu bar. First run: click the icon → **Set API Keys…** (no terminal needed)
and grant the permissions below.

An unsigned app trips Gatekeeper on other people's Macs ("can't be opened").
For yourself: right-click → Open, or `xattr -dr com.apple.quarantine
/Applications/ScreenJarvis.app`. To distribute, sign + notarize (below).

## What the bundle declares (`packaging/setup_app.py`)

- `LSUIElement = True` — menu-bar accessory: no Dock icon, no ⌘-Tab entry, and
  it never steals focus, which is what lets **auto-paste** land in the app you
  were typing in.
- `NSMicrophoneUsageDescription` and `NSAppleEventsUsageDescription` — the text
  macOS shows when it asks for the microphone and for Automation (auto-paste
  drives System Events). Screen Recording, Accessibility, and Input Monitoring
  are granted at runtime via TCC and need no Info.plist string.
- Bundle id `com.screenjarvis.app`, version from `VERSION` in that file.

## Permissions on first run

Same four panes as the terminal version, but now granted to **ScreenJarvis**
(System Settings → Privacy & Security): **Microphone**, **Screen Recording**,
**Accessibility**, **Input Monitoring** — plus **Automation → System Events**
the first time auto-paste fires. After granting **Screen Recording**, quit and
relaunch once so it takes effect.

## Signing & notarization (to share with others)

Requires a paid Apple Developer account (a "Developer ID Application"
certificate in your keychain) and a stored notarytool credential:

```sh
# one time: store an app-specific password under a profile name
xcrun notarytool store-credentials sj-notary \
  --apple-id you@example.com --team-id TEAMID --password APP_SPECIFIC_PW

SJ_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
SJ_NOTARY_PROFILE="sj-notary" \
  ./scripts/build_app.sh
```

With those env vars set, `build_app.sh` codesigns the app with the hardened
runtime, then submits the DMG to Apple, waits, and staples the ticket to both
the DMG and the app. The result opens cleanly on any Mac.

## Notes / limits

- The app is not sandboxed — global hotkey capture, screen recording, and
  synthetic paste keystrokes are incompatible with the App Sandbox, so this is a
  Developer-ID-signed app for direct distribution, **not** a Mac App Store build.
- Start-at-login: the in-app **Start at Login** toggle writes a LaunchAgent
  pointing at the app; permissions granted to the app carry over (unlike the
  `uv run` path, where they attach to Terminal).
- Universal builds: py2app follows the interpreter it runs under. Build with a
  universal2 Python if you need one binary for Intel + Apple Silicon.
