#version 330
//__PRECISION__
// ── GL 3.3 fallback: advance every trajectory one (sub-)step per pass ────────────────
// State lives in textures (one texel per trajectory): state = (x, y, z, t_step),
// rng = xorshift state, prev = (u, v, cv, have) is maintained by the draw pass via MRT here.
uniform sampler2D  u_state;
uniform usampler2D u_rng;
uniform int   u_substeps;
uniform float u_dt;
uniform float u_t0;
uniform vec4  u_ic;
uniform float u_jitter;
uniform float u_p[__NPARAMS__];

layout(location = 0) out vec4 o_state;
layout(location = 1) out uint o_rng;
layout(location = 2) out vec4 o_old;    // previous state (x, y, z, w); x = 1e30 marks a restart

const float DIVERGE_LIMIT = 1.0e6;
//__PRELUDE__
//__STEP__

void main() {
    ivec2 tc = ivec2(gl_FragCoord.xy);
    vec4 s = texelFetch(u_state, tc, 0);
    uint rng = texelFetch(u_rng, tc, 0).r;
    real x = s.x, y = s.y, z = s.z, w = s.w;
    real tstep = R(u_t0);
    real ox = x, oy = y, oz = z, ow = w;
    for (int k = 0; k < u_substeps; k++) { step(x, y, z, w, rng, tstep, R(u_dt), x, y, z); tstep += R(1.0); }
    bool restarted = false;
    if (isnan(x) || isnan(y) || isnan(z) || isnan(w) || isinf(x) || isinf(y) || isinf(z) || isinf(w)
        || abs(x) > DIVERGE_LIMIT || abs(y) > DIVERGE_LIMIT || abs(z) > DIVERGE_LIMIT || abs(w) > DIVERGE_LIMIT) {
        x = u_ic.x + (_rand(rng) - 0.5) * u_jitter;
        y = u_ic.y + (_rand(rng) - 0.5) * u_jitter;
        z = u_ic.z + (_rand(rng) - 0.5) * u_jitter;
        w = u_ic.w;
        restarted = true;
    }
    o_state = vec4(x, y, z, w);
    o_rng = rng;
    o_old = restarted ? vec4(1e30, 0.0, 0.0, 0.0) : vec4(ox, oy, oz, ow);
}
