"""py2app build configuration for the ScreenJarvis menu-bar app.

This turns the Python package into a double-clickable ScreenJarvis.app — no
terminal, no `uv`, permissions that attach to *ScreenJarvis* rather than to
Terminal or a bare "Python". Build on macOS (see scripts/build_app.sh):

    python3 -m venv .venv-app && source .venv-app/bin/activate
    pip install -e . py2app
    python packaging/setup_app.py py2app        # -> dist/ScreenJarvis.app

scripts/build_app.sh wraps this, builds the .icns first, and wraps the result
in a DMG. Signing / notarization are documented in packaging/BUILD.md.
"""

from setuptools import setup

VERSION = "0.1.0"

APP = ["packaging/app_entry.py"]

PLIST = {
    "CFBundleName": "ScreenJarvis",
    "CFBundleDisplayName": "ScreenJarvis",
    "CFBundleIdentifier": "com.screenjarvis.app",
    "CFBundleShortVersionString": VERSION,
    "CFBundleVersion": VERSION,
    "LSMinimumSystemVersion": "12.0",
    # menu-bar accessory: no Dock icon, no app-switcher entry, never steals
    # focus (which is what lets auto-paste land in the app the user was in).
    "LSUIElement": True,
    "NSHighResolutionCapable": True,
    # Screen Recording / Accessibility / Input Monitoring are TCC-gated at
    # runtime and take no Info.plist string. The mic and Automation (auto-paste
    # drives System Events via AppleEvents) prompts show the text below.
    "NSMicrophoneUsageDescription":
        "ScreenJarvis records your voice while you hold the recording key.",
    "NSAppleEventsUsageDescription":
        "ScreenJarvis pastes your dictated text into the app you are using.",
}

OPTIONS = {
    # argv_emulation uses Carbon event handling that can hang a background app —
    # off is required for a menu-bar accessory.
    "argv_emulation": False,
    "plist": PLIST,
    "iconfile": "packaging/icon/ScreenJarvis.icns",
    "packages": [
        "screenjarvis", "rumps", "anthropic", "pydantic", "pydantic_core",
        "mss", "pynput", "sounddevice", "httpx", "httpcore", "certifi", "PIL",
    ],
    "includes": ["objc", "Foundation", "AppKit", "Quartz"],
}

setup(
    name="ScreenJarvis",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
