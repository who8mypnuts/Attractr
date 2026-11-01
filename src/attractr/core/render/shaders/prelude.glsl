// ── Attractr GLSL runtime prelude — mirrors core/formula/runtime_numba.py ──────────
// Injected before the generated step()/color_fn().  Requires #version 430 (or 330 for the
// points engine; no compute-only features are used here).

uint _xorshift(inout uint s) {
    s ^= s << 13u; s ^= s >> 17u; s ^= s << 5u;
    return s;
}
float _rand(inout uint s) { return float(_xorshift(s) >> 8u) * (1.0 / 16777216.0); }
float _randn(inout uint s) {
    float u1 = max(_rand(s), 1e-12);
    float u2 = _rand(s);
    return sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2);
}
float _log(float x)   { float a = abs(x); return a < 1e-30 ? -69.0 : log(a); }
float _log2(float x)  { return _log(x) * 1.4426950408889634; }
float _log10(float x) { return _log(x) * 0.4342944819032518; }
float _sqrt(float x)  { return sqrt(abs(x)); }
float _cbrt(float x)  { return sign(x) * pow(abs(x), 1.0 / 3.0); }
float _round(float x) { return floor(x + 0.5); }
float _pow(float a, float b) { return pow(abs(a), b) * ((a < 0.0 && fract(b * 0.5) > 0.25) ? -1.0 : 1.0); }
float _ipow2(float a) { return a * a; }
float _ipow3(float a) { return a * a * a; }
float _ipow4(float a) { float b = a * a; return b * b; }
float _hypot(float a, float b) { return length(vec2(a, b)); }
float _re_pow(float x, float y, float n) {
    int k = int(n); float rr = 1.0, ri = 0.0, bx = x, by = y;
    while (k > 0) {
        if ((k & 1) != 0) { float t = rr * bx - ri * by; ri = rr * by + ri * bx; rr = t; }
        float t2 = bx * bx - by * by; by = 2.0 * bx * by; bx = t2; k >>= 1;
    }
    return rr;
}
float _im_pow(float x, float y, float n) {
    int k = int(n); float rr = 1.0, ri = 0.0, bx = x, by = y;
    while (k > 0) {
        if ((k & 1) != 0) { float t = rr * bx - ri * by; ri = rr * by + ri * bx; rr = t; }
        float t2 = bx * bx - by * by; by = 2.0 * bx * by; bx = t2; k >>= 1;
    }
    return ri;
}
