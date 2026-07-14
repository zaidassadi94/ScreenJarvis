"""py2app entry point: launch the ScreenJarvis menu-bar app.

A bundled .app is started outside any shell and inherits no environment, so the
normal flow (cli.main -> load_config -> apply_api_keys, which makes config-file
keys authoritative) is exactly what we want here. Reuse it rather than
duplicating startup.
"""

import sys

from screenjarvis.cli import main

if __name__ == "__main__":
    sys.exit(main(["app"]))
