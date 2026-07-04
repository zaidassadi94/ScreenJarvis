"""Start-at-login via a per-user LaunchAgent.

The plist points at the *current* interpreter (`sys.executable -m screenjarvis
app`), so install must be run from the environment ScreenJarvis lives in —
which is exactly how `sj app --install-login` reaches this code.
"""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

LABEL = "com.screenjarvis.menubar"

# Deliberately no launchctl load/unload here: `unload` SIGTERMs the running
# job — which is this very app when it was started by the login item — and
# `load` with RunAtLoad immediately spawns a second instance next to a running
# one. Writing/removing the plist alone takes effect at the next login, which
# is exactly what "Start at Login" means.


def plist_path() -> Path:
    return Path("~/Library/LaunchAgents").expanduser() / f"{LABEL}.plist"


def installed() -> bool:
    return plist_path().exists()


def install_login_item() -> int:
    plist = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "screenjarvis", "app"],
        "RunAtLoad": True,
        "ProcessType": "Interactive",
    }
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(plist))
    print(f"ScreenJarvis will start at your next login (runs {sys.executable} -m screenjarvis app)")
    print(f"  {path}")
    return 0


def uninstall_login_item() -> int:
    path = plist_path()
    if path.exists():
        path.unlink()
        print(f"Removed login item {LABEL} — takes effect at next login.")
    else:
        print("No login item installed")
    return 0
