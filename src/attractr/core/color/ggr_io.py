"""GIMP gradient (.ggr) import/export.

A .ggr file lists segments: left, middle, right positions, left RGBA, right RGBA, blend
type and colouring type.  Import converts each segment to stops at its end points (plus
the midpoint when it is off-centre); export writes one linear RGB segment per stop pair.
"""

from __future__ import annotations

from pathlib import Path

from attractr.core.color.gradient import Gradient, Stop


def read_ggr(path: str | Path) -> Gradient:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or not lines[0].startswith("GIMP Gradient"):
        raise ValueError("not a GIMP gradient file")
    name = Path(path).stem
    idx = 1
    if lines[idx].startswith("Name:"):
        name = lines[idx][5:].strip()
        idx += 1
    n = int(lines[idx].strip())
    idx += 1
    stops: list[Stop] = []
    for line in lines[idx : idx + n]:
        f = [float(v) for v in line.split()[:13]]
        left, mid, right = f[0], f[1], f[2]
        lc, rc = f[3:7], f[7:11]
        if not stops or abs(stops[-1].pos - left) > 1e-6:
            stops.append(Stop(left, *lc))
        if abs(mid - (left + right) / 2) > 1e-3:
            m = [(a + b) / 2 for a, b in zip(lc, rc, strict=True)]
            stops.append(Stop(mid, *m))
        stops.append(Stop(right, *rc))
    dedup: list[Stop] = []
    for s in stops:
        if dedup and abs(dedup[-1].pos - s.pos) < 1e-6:
            dedup[-1] = s
        else:
            dedup.append(s)
    return Gradient(tuple(dedup), "rgb", False, name)


def write_ggr(g: Gradient, path: str | Path) -> Path:
    path = Path(path)
    segs = []
    for a, b in zip(g.stops, g.stops[1:], strict=False):
        mid = (a.pos + b.pos) / 2
        segs.append(f"{a.pos:.6f} {mid:.6f} {b.pos:.6f} {a.r:.6f} {a.g:.6f} {a.b:.6f} {a.a:.6f} {b.r:.6f} {b.g:.6f} {b.b:.6f} {b.a:.6f} 0 0")
    path.write_text("GIMP Gradient\n" + f"Name: {g.name}\n" + f"{len(segs)}\n" + "\n".join(segs) + "\n", encoding="utf-8")
    return path
