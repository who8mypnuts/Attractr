"""Entry point: ``attractr`` opens the GUI when no sub-command is given, else runs the CLI."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args == ["gui"] or (len(args) >= 1 and args[0].endswith(".attractr")):
        return main_gui(args)
    from attractr.cli.main import run

    return run(args)


def main_gui(argv: list[str] | None = None) -> int:
    from attractr.app import run_gui

    return run_gui(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
