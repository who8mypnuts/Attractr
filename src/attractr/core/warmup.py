"""Pre-compile numba kernels for all built-in attractors (fills the on-disk cache).

Run in a *separate process* (``attractr warmup`` / QProcess from the GUI) so the heavy,
GIL-holding compilation never stalls the user interface.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

from attractr.core.attractors.registry import registry
from attractr.core.io.paths import cache_dir


def marker_path():
    from attractr.version import __version__

    return cache_dir("numba") / f"warm_{__version__}.ok"


def is_warm() -> bool:
    return marker_path().exists()


def warm_all(on_progress: Callable[[int, int, str], None] | None = None, include_accumulate: bool = True) -> int:
    """Compile step + sample_points (+ optionally the CPU accumulate kernel) for every
    built-in.  Returns the number of attractors processed."""
    import numpy as np

    from attractr.core.render.engines.cpu_compile import kernel_module

    specs = [s for s in registry.all() if s.builtin]
    for i, spec in enumerate(specs):
        if on_progress:
            on_progress(i, len(specs), spec.id)
        try:
            cf = spec.compiled("rk4")
            mod = kernel_module(cf)
            p = spec.params_array()
            rs = np.ones(4, dtype=np.uint32)
            mod.step(0.1, 0.1, 0.1, 0.0, p, rs, 0, 0.0, spec.dt, 0.1, 0.1, 0.1)
            X = np.full(4, 0.1)
            out = np.zeros((4 * 2, 7))
            mod.sample_points(X.copy(), X.copy(), X.copy(), np.zeros(4), np.zeros(4), rs, p, spec.dt, 1, 2, 0.0, out, np.zeros(4, dtype=np.int64), np.zeros(3), 0.1)
            # the default (gas) accumulate variant is what previews and thumbnails use
            if include_accumulate:
                from attractr.core.render.engines.cpu_numba import CpuEngine
                from attractr.core.render.pipeline import default_settings
                from attractr.core.render.settings import Quality

                CpuEngine().accumulate(default_settings(spec, Quality(width=16, height=16, points_per_pixel=1)), spec)
        except Exception as exc:  # noqa: BLE001
            print(f"warmup failed for {spec.id}: {exc}", file=sys.stderr)
    marker_path().write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
    return len(specs)


def main(argv: list[str] | None = None) -> int:
    quiet = "--quiet" in (argv or sys.argv[1:])
    full = "--full" in (argv or sys.argv[1:])

    def prog(i, n, sid):
        if not quiet:
            print(f"[{i + 1}/{n}] {sid}", flush=True)

    n = warm_all(prog, include_accumulate=full)
    if not quiet:
        print(f"warmed {n} attractors")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
