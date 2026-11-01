# ── CPU KERNEL TEMPLATE ──────────────────────────────────────────────────────────
# This file is *appended as text* to the generated formula module (which defines
# ``step`` and ``color_fn``) and compiled by numba.  It is kept as a real .py file so it
# stays readable, lint-able and diff-able.  Do not import it directly.
#
# Buffers are (T, Hs, Ws) float32 — one private slice per thread, merged afterwards.
# Unused buffers are passed as (1, 1, 1) dummies and never written (flags guard them).

from numba import prange  # noqa: E402,F401

DIVERGE_LIMIT = 1.0e6
# Compile-time configuration (replaced per kernel variant by cpu_compile — module globals
# are constants for numba, so the unused accumulation buffers and their stores vanish and
# the compiler no longer has to assume they alias the count buffer: ~3× faster).
WANT_DEPTH = __WANT_DEPTH__
WANT_ZMIN = __WANT_ZMIN__
WANT_COLOR = __WANT_COLOR__
SPLAT_R = __SPLAT_R__


@njit(cache=True, nogil=True, inline="always")
def _deposit(cnt, dep, zmn, cvb, t, px, py, w, depth, cv):
    cnt[t, py, px] += w
    if WANT_DEPTH:
        dep[t, py, px] += w * depth
    if WANT_ZMIN:
        if depth < zmn[t, py, px]:
            zmn[t, py, px] = depth
    if WANT_COLOR:
        cvb[t, py, px] += w * cv


@njit(cache=True, nogil=True, inline="always")
def _splat(cnt, dep, zmn, cvb, t, Ws, Hs, u, v, w, depth, cv, kern):
    """Deposit weight ``w`` at continuous pixel position (u, v).  SPLAT_R == 0 → bilinear
    anti-aliased 2×2 splat; SPLAT_R ≥ 1 → (2r+1)² soft-disk kernel (weights sum to 1)."""
    landed = 0.0
    r = SPLAT_R
    if SPLAT_R == 0:
        gx = u - 0.5
        gy = v - 0.5
        x0 = int(math.floor(gx))
        y0 = int(math.floor(gy))
        fx = gx - x0
        fy = gy - y0
        for j in range(2):
            yy = y0 + j
            if yy < 0 or yy >= Hs:
                continue
            wy = fy if j == 1 else 1.0 - fy
            for i2 in range(2):
                xx = x0 + i2
                if xx < 0 or xx >= Ws:
                    continue
                wx = fx if i2 == 1 else 1.0 - fx
                ww = w * wx * wy
                _deposit(cnt, dep, zmn, cvb, t, xx, yy, ww, depth, cv)
                landed += ww
    else:
        ix = int(math.floor(u))
        iy = int(math.floor(v))
        kn = 2 * r + 1
        for dy in range(-r, r + 1):
            yy = iy + dy
            if yy < 0 or yy >= Hs:
                continue
            for dx in range(-r, r + 1):
                xx = ix + dx
                if xx < 0 or xx >= Ws:
                    continue
                k = kern[(dy + r) * kn + (dx + r)]
                if k == 0.0:
                    continue
                ww = w * k
                _deposit(cnt, dep, zmn, cvb, t, xx, yy, ww, depth, cv)
                landed += ww
    return landed


@njit(cache=True, nogil=True, inline="always")
def _color_value(code, qx, qy, qz, speed, radius, curv, idx_frac, fx, fy, fz, p):
    if code == 1:
        return qx
    if code == 2:
        return qy
    if code == 3:
        return qz
    if code == 4:
        return qz
    if code == 5:
        return speed
    if code == 6:
        return radius
    if code == 7:
        return idx_frac
    if code == 8:
        return curv
    if code == 9:
        return color_fn(fx, fy, fz, p)
    return 0.0


@njit(cache=True, nogil=True, inline="always")
def _reseed(X, Y, Z, RS, i, ic, jitter):
    X[i] = ic[0] + (_rand(RS, i) - 0.5) * jitter
    Y[i] = ic[1] + (_rand(RS, i) - 0.5) * jitter
    Z[i] = ic[2] + (_rand(RS, i) - 0.5) * jitter


@njit(nogil=True, cache=True)
def accumulate(
    t, lo, hi,
    X, Y, Z, RS, PU, PV, PC, HAVE, DXp, DYp, DZp,
    p, dt, substeps, steps, t0,
    R, center, inv_radius, cx, cy, focal, persp, Ws, Hs,
    kern, gap_fill, color_code, do_plot,
    cnt, dep, zmn, cvb, restarts, plotted, ic, jitter,
):
    """Run trajectories [lo, hi) for ``steps`` steps, depositing into buffer slice ``t``.
    Called from several Python threads at once (nogil) with disjoint slices.  The buffer
    set and splat radius are compile-time constants of this kernel variant."""
    n = X.shape[0]
    inv_n = 1.0 / max(n, 1)
    plotted_t = 0.0
    restarts_t = 0
    for i in range(lo, hi):
        x = X[i]
        y = Y[i]
        z = Z[i]
        pu = PU[i]
        pv = PV[i]
        pc = PC[i]
        have = HAVE[i]
        dxp = DXp[i]
        dyp = DYp[i]
        dzp = DZp[i]
        tstep = t0
        idx_frac = i * inv_n
        for s in range(steps):
            ox = x
            oy = y
            oz = z
            for _k in range(substeps):
                x, y, z = step(x, y, z, p, RS, i, tstep, dt)
                tstep += 1.0
            # ── divergence guard ───────────────────────────────────────────────
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)) or (
                abs(x) > DIVERGE_LIMIT or abs(y) > DIVERGE_LIMIT or abs(z) > DIVERGE_LIMIT
            ):
                _reseed(X, Y, Z, RS, i, ic, jitter)
                x = X[i]
                y = Y[i]
                z = Z[i]
                restarts_t += 1
                have = 0
                continue
            if not do_plot:
                continue
            # ── project ───────────────────────────────────────────────────────
            ux = (x - center[0]) * inv_radius
            uy = (y - center[1]) * inv_radius
            uz = (z - center[2]) * inv_radius
            qx = R[0] * ux + R[1] * uy + R[2] * uz
            qy = R[3] * ux + R[4] * uy + R[5] * uz
            qz = R[6] * ux + R[7] * uy + R[8] * uz
            d = 1.0 + persp * qz
            if d < 0.05:
                d = 0.05
            u = cx + focal * qx / d
            v = cy - focal * qy / d
            if not (u > -1.0e6 and u < 1.0e6 and v > -1.0e6 and v < 1.0e6):
                have = 0
                continue
            # ── colour value ───────────────────────────────────────────────────
            cv = 0.0
            if WANT_COLOR:
                ddx = x - ox
                ddy = y - oy
                ddz = z - oz
                speed = math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) * inv_radius
                curv = 0.5
                if color_code == 8:
                    la = speed
                    lb = math.sqrt(dxp * dxp + dyp * dyp + dzp * dzp) * inv_radius
                    if la > 1e-12 and lb > 1e-12:
                        cosa = (ddx * dxp + ddy * dyp + ddz * dzp) * inv_radius * inv_radius / (la * lb)
                        if cosa > 1.0:
                            cosa = 1.0
                        elif cosa < -1.0:
                            cosa = -1.0
                        curv = 0.5 * (1.0 - cosa)  # 0 straight … 1 sharp turn
                    dxp = ddx
                    dyp = ddy
                    dzp = ddz
                radius = math.sqrt(qx * qx + qy * qy + qz * qz)
                cv = _color_value(color_code, qx, qy, qz, speed, radius, curv, idx_frac, x, y, z, p)
            # ── splat (with optional gap filling to the previous point) ────────
            nseg = 1
            if gap_fill and have != 0:
                ddu = u - pu
                ddv = v - pv
                dist = math.sqrt(ddu * ddu + ddv * ddv)
                if dist > 1.0 and dist < (Ws + Hs):
                    nseg = int(math.ceil(dist))
                    if nseg > 64:
                        nseg = 64
            if nseg == 1:
                plotted_t += _splat(cnt, dep, zmn, cvb, t, Ws, Hs, u, v, 1.0, qz, cv, kern)
            else:
                wseg = 1.0 / nseg
                for j in range(1, nseg + 1):
                    f = j * wseg
                    uu = pu + (u - pu) * f
                    vv = pv + (v - pv) * f
                    cc = pc + (cv - pc) * f
                    plotted_t += _splat(cnt, dep, zmn, cvb, t, Ws, Hs, uu, vv, wseg, qz, cc, kern)
            pu = u
            pv = v
            pc = cv
            have = 1
        X[i] = x
        Y[i] = y
        Z[i] = z
        PU[i] = pu
        PV[i] = pv
        PC[i] = pc
        HAVE[i] = have
        DXp[i] = dxp
        DYp[i] = dyp
        DZp[i] = dzp
    plotted[t] += plotted_t
    restarts[t] += restarts_t


@njit(nogil=True, cache=True)
def sample_points(X, Y, Z, RS, p, dt, substeps, steps, t0, out, restarts, ic, jitter):  # noqa: E501
    """Advance every trajectory ``steps`` times, writing each visited point into
    ``out[i*steps + s, :]`` (used for framing / analysis).  Divergent trajectories are
    re-seeded and their slots filled with NaN."""
    n = X.shape[0]
    for i in range(n):
        x = X[i]
        y = Y[i]
        z = Z[i]
        tstep = t0
        for s in range(steps):
            for _k in range(substeps):
                x, y, z = step(x, y, z, p, RS, i, tstep, dt)
                tstep += 1.0
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)) or (
                abs(x) > DIVERGE_LIMIT or abs(y) > DIVERGE_LIMIT or abs(z) > DIVERGE_LIMIT
            ):
                _reseed(X, Y, Z, RS, i, ic, jitter)
                x = X[i]
                y = Y[i]
                z = Z[i]
                restarts[i] += 1
                out[i * steps + s, 0] = np.nan
                out[i * steps + s, 1] = np.nan
                out[i * steps + s, 2] = np.nan
                continue
            out[i * steps + s, 0] = x
            out[i * steps + s, 1] = y
            out[i * steps + s, 2] = z
        X[i] = x
        Y[i] = y
        Z[i] = z


@njit(nogil=True, cache=True)
def lyapunov_kernel(x, y, z, p, RS, dt, substeps, steps, d0, renorm_every):
    """Largest Lyapunov exponent by the two-trajectory (Benettin) method.
    Returns (sum of log stretch factors, number of renormalisations, diverged flag).
    The exponent is  sum / (renorms · renorm_every · substeps · dt)  for flows and
    sum / (renorms · renorm_every · substeps) per iteration for maps."""
    x2 = x + d0
    y2 = y
    z2 = z
    total = 0.0
    renorms = 0
    tstep = 0.0
    for s in range(steps):
        for _k in range(substeps):
            x, y, z = step(x, y, z, p, RS, 0, tstep, dt)
            x2, y2, z2 = step(x2, y2, z2, p, RS, 1, tstep, dt)
            tstep += 1.0
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)) or abs(x) > DIVERGE_LIMIT or abs(y) > DIVERGE_LIMIT or abs(z) > DIVERGE_LIMIT:
            return total, renorms, 1
        if (s + 1) % renorm_every == 0:
            dx = x2 - x
            dy = y2 - y
            dz = z2 - z
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d <= 0.0 or not math.isfinite(d):
                return total, renorms, 1
            total += math.log(d / d0)
            renorms += 1
            f = d0 / d
            x2 = x + dx * f
            y2 = y + dy * f
            z2 = z + dz * f
    return total, renorms, 0
