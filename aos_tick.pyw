"""Entry point for the Windows scheduled task: runs `aos tick` without a console window (pythonw).

Errors go to data/tick.log, because pythonw has no output (print would be lost silently there).
"""

import contextlib
import io
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
LOG = ROOT / "data" / "tick.log"
MAX_LOG_BYTES = 200_000


def _log(text: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        if LOG.stat().st_size > MAX_LOG_BYTES:
            LOG.write_text("", encoding="utf-8")
    except OSError:
        pass
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")


def run() -> int:
    try:
        from aos.cli import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            # the config next to this file: the scheduled task has no $AOS_HOME or $AOS_CONFIG of your shell
            rc = main(["--config", str(ROOT / "aos.toml"), "tick", "--quiet"])
        if rc:  # e.g. "Error: routines.toml is not valid TOML"
            _log(buf.getvalue().strip() or f"aos tick exited with code {rc}")
        return rc
    except Exception:  # noqa: BLE001 - nothing may stop the scheduler silently
        _log(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(run())
