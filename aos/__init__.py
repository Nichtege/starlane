"""Starlane: a small operating system around your notes vault and Claude Code (MAPS: Memory, Agent, Pulse, Screen)."""

import sys

if sys.version_info < (3, 11):  # before anything imports tomllib: say what to do instead of a traceback
    sys.exit(
        f"Starlane needs Python 3.11 or newer (this is {sys.version.split()[0]}). "
        "Install a newer Python and start it by its own name, for example: python3.12 -m aos"
    )

__version__ = "1.3.0"
