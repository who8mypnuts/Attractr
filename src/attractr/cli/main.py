"""``attractr`` command line interface."""

from __future__ import annotations

import argparse
import logging
import sys

from attractr.version import __version__


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="attractr", description="Attractr — strange attractor studio (CLI). Run without a sub-command to open the GUI.")
    ap.add_argument("--version", action="version", version=f"attractr {__version__}")
    ap.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = ap.add_subparsers(dest="command")

    from attractr.cli import cmd_animate, cmd_info, cmd_list, cmd_render, cmd_report

    cmd_render.add_parser(sub)
    cmd_list.add_parser(sub)
    cmd_info.add_parser(sub)
    cmd_report.add_parser(sub)
    cmd_animate.add_parser(sub)
    wp = sub.add_parser("warmup", help="pre-compile numba kernels for all built-in attractors")
    wp.add_argument("--full", action="store_true", help="also compile the CPU accumulation kernels")
    wp.add_argument("--quiet", action="store_true")
    wp.set_defaults(func=lambda a: __import__("attractr.core.warmup", fromlist=["main"]).main(["--quiet"] * a.quiet + ["--full"] * a.full))
    return ap


def run(argv: list[str]) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if not args.command:
        ap.print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
