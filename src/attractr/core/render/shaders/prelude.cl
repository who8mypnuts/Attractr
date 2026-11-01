// ── Attractr OpenCL runtime prelude — mirrors runtime_numba.py / prelude.glsl ───────
uint _xorshift(uint* s) { uint v = *s; v ^= v << 13; v ^= v >> 17; v ^= v << 5; *s = v; return v; }
float _rand(uint* s) { return (float)(_xorshift(s) >> 8) * (1.0f / 16777216.0f); }
float _randn(uint* s) { float u1 = fmax(_rand(s), 1e-12f); float u2 = _rand(s); return sqrt(-2.0f * log(u1)) * cos(6.283185307179586f * u2); }
float _log(float x)   { float a = fabs(x); return a < 1e-30f ? -69.0f : log(a); }
float _log2(float x)  { return _log(x) * 1.4426950408889634f; }
float _log10(float x) { return _log(x) * 0.4342944819032518f; }
float _sqrt(float x)  { return sqrt(fabs(x)); }
float _cbrt(float x)  { return cbrt(x); }
float _sign(float x)  { return x > 0.0f ? 1.0f : (x < 0.0f ? -1.0f : 0.0f); }
float _round(float x) { return floor(x + 0.5f); }
float _fract(float x) { return x - floor(x); }
float _mod(float a, float b) { return b == 0.0f ? 0.0f : a - b * floor(a / b); }
float _pow(float a, float b) { return pow(fabs(a), b) * ((a < 0.0f && _fract(b * 0.5f) > 0.25f) ? -1.0f : 1.0f); }
float _ipow2(float a) { return a * a; }
float _ipow3(float a) { return a * a * a; }
float _ipow4(float a) { float b = a * a; return b * b; }
float _min(float a, float b) { return fmin(a, b); }
float _max(float a, float b) { return fmax(a, b); }
float _clamp(float x, float lo, float hi) { return fmin(fmax(x, lo), hi); }
float _mix(float a, float b, float t) { return a + (b - a) * t; }
float _smoothstep(float e0, float e1, float x) { if (e1 == e0) return x < e0 ? 0.0f : 1.0f; float t = _clamp((x - e0) / (e1 - e0), 0.0f, 1.0f); return t * t * (3.0f - 2.0f * t); }
float _step(float e, float x) { return x < e ? 0.0f : 1.0f; }
float _hypot(float a, float b) { return hypot(a, b); }
float _re_pow(float x, float y, float n) { int k = (int)n; float rr = 1.0f, ri = 0.0f, bx = x, by = y;
    while (k > 0) { if (k & 1) { float t = rr * bx - ri * by; ri = rr * by + ri * bx; rr = t; } float t2 = bx * bx - by * by; by = 2.0f * bx * by; bx = t2; k >>= 1; } return rr; }
float _im_pow(float x, float y, float n) { int k = (int)n; float rr = 1.0f, ri = 0.0f, bx = x, by = y;
    while (k > 0) { if (k & 1) { float t = rr * bx - ri * by; ri = rr * by + ri * bx; rr = t; } float t2 = bx * bx - by * by; by = 2.0f * bx * by; bx = t2; k >>= 1; } return ri; }
#define abs(x) fabs(x)
#define sign(x) _sign(x)
