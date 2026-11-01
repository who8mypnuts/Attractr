"""``attractr info`` — hardware / engine probe, and ``attractr lyapunov``."""

from __future__ import annotations

import json
import os
import platform

from attractr.core.attractors.registry import registry
from attractr.core.render.engines import selector
from attractr.version import __version__


def add_parser(sub) -> None:
    ap = sub.add_parser("info", help="system and engine information")
    ap.add_argument("--json", action="store_true")
    ap.set_defaults(func=run_info)

    lp = sub.add_parser("lyapunov", help="estimate the largest Lyapunov exponent of an attractor")
    lp.add_argument("target", nargs="?", default="lorenz")
    lp.add_argument("--param", "-p", action="append", default=[], metavar="NAME=VALUE")
    lp.add_argument("--steps", type=int, default=40000)
    lp.add_argument("--dt", type=float)
    lp.add_argument("--json", action="store_true")
    lp.set_defaults(func=run_lyapunov)


def system_info() -> dict:
    import numba
    import numpy

    info = {
        "attractr": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_threads": os.cpu_count(),
        "numba": numba.__version__,
        "numpy": numpy.__version__,
        "numba_threads": numba.get_num_threads(),
        "engines": {k: v.__dict__ for k, v in selector.probe_all().items()},
    }
    return info


def run_info(a) -> int:
    info = system_info()
    if a.json:
        print(json.dumps(info, indent=1, default=str))
        return 0
    print(f"Attractr {info['attractr']} · Python {info['python']} · {info['platform']}")
    print(f"CPU threads: {info['cpu_threads']} (numba uses {info['numba_threads']}) · numba {info['numba']} · numpy {info['numpy']}")
    print("Engines:")
    for k, c in info["engines"].items():
        flag = "✓" if c["available"] else "✗"
        bench = f"{c['mpts_per_second']:.1f} Mpts/s" if c.get("mpts_per_second") else ""
        print(f"  {flag} {k:14s} {c['name']:28s} {c['device']}  {bench}  {'; '.join(c['notes'])}")
    return 0


def run_lyapunov(a) -> int:
    from attractr.core.analysis.lyapunov import largest_exponent

    spec = registry.get(a.target)
    params = {}
    for item in a.param:
        k, v = item.split("=", 1)
        params[k] = float(v)
    r = largest_exponent(spec, params, dt=a.dt, steps=a.steps)
    if a.json:
        print(json.dumps(r.__dict__))
    else:
        unit = "per unit time" if spec.is_flow else "per iteration"
        print(f"{spec.name}: λ₁ ≈ {r.exponent:.4f} {unit} → {r.label}")
    return 0
