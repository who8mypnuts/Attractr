"""Logging to ``~/.attractr/logs`` + a native-crash trace.

Every run (GUI or CLI) appends INFO-level logs to ``attractr.log`` (rotated at 2 MB) —
render plans, engine choices, GPU budgets, fallbacks — and enables :mod:`faulthandler`
into ``crash.log`` so that a segfault or an abort inside a GPU driver, numba or Qt leaves
a Python stack trace instead of a silent exit.  Pass the two files along when reporting
a crash."""

from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import platform
import sys

from attractr.core.io.paths import logs_dir
from attractr.version import __version__

_crash_file = None  # keep the handle alive for faulthandler


def setup_logging(console_level: int = logging.WARNING) -> None:
    """Configure console + rotating-file logging and the ``faulthandler`` crash trace (idempotent per process)."""
    global _crash_file
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stderr for h in root.handlers):
        con = logging.StreamHandler(sys.stderr)
        con.setLevel(console_level)
        con.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(con)
    if _crash_file is not None:
        return  # already set up in this process (GUI and CLI share one entry point)
    try:
        d = logs_dir()
        d.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(d / "attractr.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        root.addHandler(fh)
        _crash_file = open(d / "crash.log", "a", encoding="utf-8")  # noqa: SIM115 — must stay open
        _crash_file.write(f"\n=== Attractr {__version__} · Python {platform.python_version()} · {platform.platform()} ===\n")
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)
    except OSError as exc:  # a read-only home must not stop the program
        root.warning("file logging unavailable: %s", exc)
    logging.getLogger(__name__).info("Attractr %s starting (%s)", __version__, " ".join(sys.argv[:3]))
