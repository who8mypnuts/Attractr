// ── Attractr iteration kernel (OpenCL 1.2) — same algorithm as iterate.comp ─────────
//__PRECISION__
//__PRELUDE__
//__STEP__

#define FIXED 256.0f
#define DIVERGE_LIMIT 1.0e6

typedef struct {
    int steps, substeps, splat_r, gap_fill, color_code;
    int want_depth, want_zmin, want_color, do_plot;
    int w, h, n;
    float dt, inv_radius, cx, cy, focal, persp, jitter, inv_n;
    float cv_lo, cv_inv_range, t0;
    float R[9], center[3], ic[4];
    float esc_lo[3], esc_hi[3], esc_cfg[3];   // escape kind: region box, (bailout², max_iter, min_iter)
} Params;

inline uint _zkey(float z) { uint k = as_uint(z); return (k & 0x80000000u) ? ~k : (k | 0x80000000u); }

inline void deposit(__global uint* cnt, __global uint* dep, __global uint* zmn, __global uint* cvb,
                    __constant Params* P, int px, int py, float w, float depth, float cv) {
    int idx = py * P->w + px;
    atomic_add(&cnt[idx], (uint)(w * FIXED + 0.5f));
    if (P->want_depth) atomic_add(&dep[idx], (uint)(w * (_clamp(depth, -2.0f, 2.0f) * 0.25f + 0.5f) * FIXED + 0.5f));
    if (P->want_zmin) atomic_min(&zmn[idx], _zkey(depth));
    if (P->want_color) atomic_add(&cvb[idx], (uint)(w * _clamp((cv - P->cv_lo) * P->cv_inv_range, 0.0f, 1.0f) * FIXED + 0.5f));
}

inline float splat(__global uint* cnt, __global uint* dep, __global uint* zmn, __global uint* cvb,
                   __constant Params* P, __constant float* kern, float u, float v, float w, float depth, float cv) {
    float landed = 0.0f;
    if (P->splat_r == 0) {
        float gx = u - 0.5f, gy = v - 0.5f;
        int x0 = (int)floor(gx), y0 = (int)floor(gy);
        float fx = gx - (float)x0, fy = gy - (float)y0;
        for (int j = 0; j < 2; j++) {
            int yy = y0 + j; if (yy < 0 || yy >= P->h) continue;
            float wy = (j == 1) ? fy : 1.0f - fy;
            for (int i = 0; i < 2; i++) {
                int xx = x0 + i; if (xx < 0 || xx >= P->w) continue;
                float wx = (i == 1) ? fx : 1.0f - fx;
                float ww = w * wx * wy;
                deposit(cnt, dep, zmn, cvb, P, xx, yy, ww, depth, cv); landed += ww;
            }
        }
    } else {
        int ix = (int)floor(u), iy = (int)floor(v), r = P->splat_r, kn = 2 * r + 1;
        for (int dy = -r; dy <= r; dy++) {
            int yy = iy + dy; if (yy < 0 || yy >= P->h) continue;
            for (int dx = -r; dx <= r; dx++) {
                int xx = ix + dx; if (xx < 0 || xx >= P->w) continue;
                float k = kern[(dy + r) * kn + (dx + r)]; if (k == 0.0f) continue;
                deposit(cnt, dep, zmn, cvb, P, xx, yy, w * k, depth, cv); landed += w * k;
            }
        }
    }
    return landed;
}

inline bool section_crossed(float sv, float psec) {   // sign change filtered by SECTION_DIR (0 both, 1 up, 2 down)
    if (!(sv * psec < 0.0f)) return false;
    if (SECTION_DIR == 1) return sv > 0.0f;
    if (SECTION_DIR == 2) return sv < 0.0f;
    return true;
}

inline float color_value(__constant float* p, int code, float qx, float qy, float qz, float speed, float radius,
                         float curv, float idx, real x, real y, real z, real w) {
    switch (code) {
        case 1: return qx; case 2: return qy; case 3: return qz; case 4: return qz;
        case 5: return speed; case 6: return radius; case 7: return idx; case 8: return curv;
        case 9: return (float)color_fn(p, x, y, z, w);
    }
    return 0.0f;
}

inline void escape_start(__constant Params* P, uint* rng, real* x0, real* y0, real* z0) {
    *x0 = R(P->esc_lo[0]) + _rand(rng) * R(P->esc_hi[0] - P->esc_lo[0]);
    *y0 = R(P->esc_lo[1]) + _rand(rng) * R(P->esc_hi[1] - P->esc_lo[1]);
    *z0 = R(P->esc_lo[2]) + _rand(rng) * R(P->esc_hi[2] - P->esc_lo[2]);
}

__kernel void iterate(__global real4* st, __global uint* rng_state, __global float4* prev, __global float4* prevd,
                      __global uint* stats, __global uint* cnt, __global uint* dep, __global uint* zmn, __global uint* cvb,
                      __constant Params* P, __constant float* kern, __constant float* p, __global float4* esc) {
    int i = get_global_id(0);
    if (i >= P->n) return;
    real4 s = st[i];
    real x = s.x, y = s.y, z = s.z, w = s.w;
    real tstep = (real)P->t0;
    real dt = (real)P->dt;
    uint rng = rng_state[i];
    float4 pv = prev[i];
    float4 pd = prevd[i];
    float plotted = 0.0f;
    real x0 = R(0.0), y0 = R(0.0), z0 = R(0.0);
    int emode = 0, ecnt = 0, enrep = 0;
#if KIND_ESCAPE
    float4 e0 = esc[2 * i], e1 = esc[2 * i + 1];
    x0 = R(e0.x); y0 = R(e0.y); z0 = R(e0.z);
    emode = (int)e1.x; ecnt = (int)e1.y; enrep = (int)e1.z;
#endif
    for (int n = 0; n < P->steps; n++) {
        real ox = x, oy = y, oz = z;
        for (int k = 0; k < P->substeps; k++) { step(p, &x, &y, &z, &w, &rng, tstep, dt, x0, y0, z0); tstep += R(1.0); }
        real sx, sy, sz, sw;
        float have_next = 1.0f;
#if KIND_ESCAPE
        ecnt += 1;
        bool finite = isfinite(x) && isfinite(y) && isfinite(z);
        if (emode == 0) {
            if (!finite || (float)(x * x + y * y + z * z) > P->esc_cfg[0]) {
                if ((float)(ecnt - 1) >= P->esc_cfg[2] && ecnt > 1) {
                    emode = 1; enrep = ecnt - 1; ecnt = 0;
                    x = x0; y = y0; z = z0; w = R((float)enrep);
                } else {
                    escape_start(P, &rng, &x0, &y0, &z0);
                    x = x0; y = y0; z = z0; ecnt = 0;
                }
            } else if ((float)ecnt >= P->esc_cfg[1]) {
                escape_start(P, &rng, &x0, &y0, &z0);
                x = x0; y = y0; z = z0; ecnt = 0;
            }
            pv.w = 0.0f;
            continue;
        }
        sx = x; sy = y; sz = z; sw = w;
        if (ecnt >= enrep || !finite) {
            emode = 0;
            escape_start(P, &rng, &x0, &y0, &z0);
            x = x0; y = y0; z = z0; ecnt = 0;
            have_next = 0.0f;
        }
        if (!P->do_plot) { pv.w = 0.0f; continue; }
        real fx = sx, fy = sy, fz = sz;
#if HAS_PLOT
        plot_fn(p, sx, sy, sz, sw, &fx, &fy, &fz);
#endif
#else
        if (!isfinite(x) || !isfinite(y) || !isfinite(z) || !isfinite(w) || fabs(x) > R(DIVERGE_LIMIT) || fabs(y) > R(DIVERGE_LIMIT) || fabs(z) > R(DIVERGE_LIMIT) || fabs(w) > R(DIVERGE_LIMIT)) {
            x = R(P->ic[0]) + (_rand(&rng) - R(0.5)) * R(P->jitter);
            y = R(P->ic[1]) + (_rand(&rng) - R(0.5)) * R(P->jitter);
            z = R(P->ic[2]) + (_rand(&rng) - R(0.5)) * R(P->jitter);
            w = R(P->ic[3]);
            atomic_inc(&stats[0]);
            pv.w = 0.0f;
            continue;
        }
#if HAS_SECTION
        float sv = (float)section_fn(p, x, y, z, w);
        bool crossed = section_crossed(sv, pd.w);
        pd.w = sv;
        if (!crossed) continue;
#endif
        if (!P->do_plot) {
#if HAS_EVENT
            event_fn(p, &x, &y, &z, &w, &rng);
#endif
            continue;
        }
        real fx = x, fy = y, fz = z;
#if HAS_PLOT
        plot_fn(p, x, y, z, w, &fx, &fy, &fz);
#endif
        sx = x; sy = y; sz = z; sw = w;   // state at the plotted point (the event may change it)
#if HAS_EVENT
        event_fn(p, &x, &y, &z, &w, &rng);
#endif
#endif
        float ux = (float)((fx - R(P->center[0])) * R(P->inv_radius)), uy = (float)((fy - R(P->center[1])) * R(P->inv_radius)), uz = (float)((fz - R(P->center[2])) * R(P->inv_radius));
        float qx = P->R[0] * ux + P->R[1] * uy + P->R[2] * uz;
        float qy = P->R[3] * ux + P->R[4] * uy + P->R[5] * uz;
        float qz = P->R[6] * ux + P->R[7] * uy + P->R[8] * uz;
        float d = fmax(1.0f + P->persp * qz, 0.05f);
        float u = P->cx + P->focal * qx / d;
        float v = P->cy - P->focal * qy / d;
        if (!(u > -1.0e6f && u < 1.0e6f && v > -1.0e6f && v < 1.0e6f)) { pv.w = 0.0f; continue; }
        float cv = 0.0f;
        if (P->want_color) {
            float ddx = (float)(sx - ox), ddy = (float)(sy - oy), ddz = (float)(sz - oz);
            float la = sqrt(ddx * ddx + ddy * ddy + ddz * ddz);
            float speed = la * P->inv_radius;
            float curv = 0.5f;
            if (P->color_code == 8) {
                float lb = sqrt(pd.x * pd.x + pd.y * pd.y + pd.z * pd.z);
                if (la > 1e-12f && lb > 1e-12f) curv = 0.5f * (1.0f - _clamp((ddx * pd.x + ddy * pd.y + ddz * pd.z) / (la * lb), -1.0f, 1.0f));
                pd.x = ddx; pd.y = ddy; pd.z = ddz;
            }
            cv = color_value(p, P->color_code, qx, qy, qz, speed, sqrt(qx * qx + qy * qy + qz * qz), curv, (float)i * P->inv_n, sx, sy, sz, sw);
        }
        int nseg = 1;
        if (P->gap_fill && pv.w > 0.0f) {
            float du = u - pv.x, dv = v - pv.y;
            float dist = sqrt(du * du + dv * dv);
            if (dist > 1.0f && dist < (float)(P->w + P->h)) nseg = min((int)ceil(dist), 64);
        }
        float wseg = 1.0f / (float)nseg;
        for (int j = 1; j <= nseg; j++) {
            float f = (float)j * wseg;
            float uu = nseg > 1 ? pv.x + (u - pv.x) * f : u;
            float vv = nseg > 1 ? pv.y + (v - pv.y) * f : v;
            float cc = nseg > 1 ? pv.z + (cv - pv.z) * f : cv;
            plotted += splat(cnt, dep, zmn, cvb, P, kern, uu, vv, wseg, qz, cc);
        }
        pv = (float4)(u, v, cv, have_next);
    }
    st[i] = (real4)(x, y, z, w);
    rng_state[i] = rng;
#if KIND_ESCAPE
    esc[2 * i] = (float4)((float)x0, (float)y0, (float)z0, 0.0f);
    esc[2 * i + 1] = (float4)((float)emode, (float)ecnt, (float)enrep, 0.0f);
#endif
    prev[i] = pv;
    prevd[i] = pd;
    uint add = (uint)(plotted * 16.0f + 0.5f);
    uint old = atomic_add(&stats[1], add);
    if (old + add < old) atomic_inc(&stats[2]);
}

__kernel void merge(__global uint* cnt, __global uint* dep, __global uint* zmn, __global uint* cvb,
                    __global float* acc_cnt, __global float* acc_dep, __global float* acc_zmn, __global float* acc_cv,
                    int npix, int want_depth, int want_zmin, int want_color, float cv_lo, float cv_range) {
    int i = get_global_id(0);
    if (i >= npix) return;
    uint c = cnt[i];
    if (c != 0u) {
        float w = (float)c / FIXED;
        acc_cnt[i] += w; cnt[i] = 0u;
        if (want_depth) { float sd = (float)dep[i] / FIXED; acc_dep[i] += (sd - 0.5f * w) * 4.0f; dep[i] = 0u; }
        if (want_color) { float sc = (float)cvb[i] / FIXED; acc_cv[i] += sc * cv_range + w * cv_lo; cvb[i] = 0u; }
    }
    if (want_zmin) {
        uint zk = zmn[i];
        if (zk != 0xFFFFFFFFu) {
            uint f = (zk & 0x80000000u) ? (zk & 0x7FFFFFFFu) : ~zk;
            float zc = as_float(f);
            acc_zmn[i] = fmin(acc_zmn[i], zc);
            zmn[i] = 0xFFFFFFFFu;
        }
    }
}
