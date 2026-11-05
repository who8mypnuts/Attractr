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

inline float color_value(__constant float* p, int code, float qx, float qy, float qz, float speed, float radius,
                         float curv, float idx, real x, real y, real z, real w) {
    switch (code) {
        case 1: return qx; case 2: return qy; case 3: return qz; case 4: return qz;
        case 5: return speed; case 6: return radius; case 7: return idx; case 8: return curv;
        case 9: return (float)color_fn(p, x, y, z, w);
    }
    return 0.0f;
}

__kernel void iterate(__global real4* st, __global uint* rng_state, __global float4* prev, __global float4* prevd,
                      __global uint* stats, __global uint* cnt, __global uint* dep, __global uint* zmn, __global uint* cvb,
                      __constant Params* P, __constant float* kern, __constant float* p) {
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
    for (int n = 0; n < P->steps; n++) {
        real ox = x, oy = y, oz = z;
        for (int k = 0; k < P->substeps; k++) { step(p, &x, &y, &z, &w, &rng, tstep, dt); tstep += R(1.0); }
        if (!isfinite(x) || !isfinite(y) || !isfinite(z) || !isfinite(w) || fabs(x) > R(DIVERGE_LIMIT) || fabs(y) > R(DIVERGE_LIMIT) || fabs(z) > R(DIVERGE_LIMIT) || fabs(w) > R(DIVERGE_LIMIT)) {
            x = R(P->ic[0]) + (_rand(&rng) - R(0.5)) * R(P->jitter);
            y = R(P->ic[1]) + (_rand(&rng) - R(0.5)) * R(P->jitter);
            z = R(P->ic[2]) + (_rand(&rng) - R(0.5)) * R(P->jitter);
            w = R(P->ic[3]);
            atomic_inc(&stats[0]);
            pv.w = 0.0f;
            continue;
        }
        if (!P->do_plot) continue;
#if HAS_SECTION
        float sv = (float)section_fn(p, x, y, z, w);
        bool crossed = sv * pd.w < 0.0f;
        pd.w = sv;
        if (!crossed) continue;
#endif
        real fx = x, fy = y, fz = z;
#if HAS_PLOT
        plot_fn(p, x, y, z, w, &fx, &fy, &fz);
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
            float ddx = (float)(x - ox), ddy = (float)(y - oy), ddz = (float)(z - oz);
            float la = sqrt(ddx * ddx + ddy * ddy + ddz * ddz);
            float speed = la * P->inv_radius;
            float curv = 0.5f;
            if (P->color_code == 8) {
                float lb = sqrt(pd.x * pd.x + pd.y * pd.y + pd.z * pd.z);
                if (la > 1e-12f && lb > 1e-12f) curv = 0.5f * (1.0f - _clamp((ddx * pd.x + ddy * pd.y + ddz * pd.z) / (la * lb), -1.0f, 1.0f));
                pd.x = ddx; pd.y = ddy; pd.z = ddz;
            }
            cv = color_value(p, P->color_code, qx, qy, qz, speed, sqrt(qx * qx + qy * qy + qz * qz), curv, (float)i * P->inv_n, x, y, z, w);
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
        pv = (float4)(u, v, cv, 1.0f);
    }
    st[i] = (real4)(x, y, z, w);
    rng_state[i] = rng;
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
