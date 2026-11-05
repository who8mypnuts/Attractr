// ── Attractr OpenCL runtime prelude — mirrors runtime_numba.py / prelude.glsl ───────
// `real` and R() come from the precision header (float or double via cl_khr_fp64).
uint _xorshift(uint* s) { uint v = *s; v ^= v << 13; v ^= v >> 17; v ^= v << 5; *s = v; return v; }
real _rand(uint* s) { return (real)(_xorshift(s) >> 8) * R(1.0 / 16777216.0); }
real _sin(real x)   { return sin(x); }
real _cos(real x)   { return cos(x); }
real _tan(real x)   { return tan(x); }
real _asin(real x)  { return asin(clamp(x, R(-1.0), R(1.0))); }
real _acos(real x)  { return acos(clamp(x, R(-1.0), R(1.0))); }
real _atan(real x)  { return atan(x); }
real _atan2(real y, real x) { return atan2(y, x); }
real _sinh(real x)  { return sinh(x); }
real _cosh(real x)  { return cosh(x); }
real _tanh(real x)  { return tanh(x); }
real _asinh(real x) { return asinh(x); }
real _acosh(real x) { return acosh(fmax(x, R(1.0))); }
real _atanh(real x) { return atanh(clamp(x, R(-0.999999), R(0.999999))); }
real _exp(real x)   { return exp(fmin(x, R(88.0))); }
real _logp(real x)  { return log(x); }
real _powp(real a, real b) { return pow(a, b); }
real _log(real x)   { real a = fabs(x); return a < R(1e-30) ? R(-69.0) : _logp(a); }
real _log2(real x)  { return _log(x) * R(1.4426950408889634); }
real _log10(real x) { return _log(x) * R(0.4342944819032518); }
real _sqrt(real x)  { return sqrt(fabs(x)); }
real _cbrt(real x)  { return cbrt(x); }
real _sign(real x)  { return x > R(0.0) ? R(1.0) : (x < R(0.0) ? R(-1.0) : R(0.0)); }
real _round(real x) { return floor(x + R(0.5)); }
real _fract(real x) { return x - floor(x); }
real _mod(real a, real b) { return b == R(0.0) ? R(0.0) : a - b * floor(a / b); }
real _pow(real a, real b) { if (a == R(0.0)) return R(0.0); real m = _powp(fabs(a), b); return (a < R(0.0) && _fract(b * R(0.5)) > R(0.25)) ? -m : m; }
real _ipow2(real a) { return a * a; }
real _ipow3(real a) { return a * a * a; }
real _ipow4(real a) { real b = a * a; return b * b; }
real _min(real a, real b) { return fmin(a, b); }
real _max(real a, real b) { return fmax(a, b); }
real _clamp(real x, real lo, real hi) { return fmin(fmax(x, lo), hi); }
real _mix(real a, real b, real t) { return a + (b - a) * t; }
real _smoothstep(real e0, real e1, real x) { if (e1 == e0) return x < e0 ? R(0.0) : R(1.0); real t = _clamp((x - e0) / (e1 - e0), R(0.0), R(1.0)); return t * t * (R(3.0) - R(2.0) * t); }
real _step(real e, real x) { return x < e ? R(0.0) : R(1.0); }
real _hypot(real a, real b) { return hypot(a, b); }
real _randn(uint* s) { real u1 = fmax(_rand(s), R(1e-12)); real u2 = _rand(s); return sqrt(R(-2.0) * _logp(u1)) * _cos(R(6.283185307179586) * u2); }
real _re_pow(real x, real y, real n) { int k = (int)n; real rr = R(1.0), ri = R(0.0), bx = x, by = y;
    while (k > 0) { if (k & 1) { real t = rr * bx - ri * by; ri = rr * by + ri * bx; rr = t; } real t2 = bx * bx - by * by; by = R(2.0) * bx * by; bx = t2; k >>= 1; } return rr; }
real _im_pow(real x, real y, real n) { int k = (int)n; real rr = R(1.0), ri = R(0.0), bx = x, by = y;
    while (k > 0) { if (k & 1) { real t = rr * bx - ri * by; ri = rr * by + ri * bx; rr = t; } real t2 = bx * bx - by * by; by = R(2.0) * bx * by; bx = t2; k >>= 1; } return ri; }
#define abs(x) fabs(x)
#define sign(x) _sign(x)
#define floor_(x) floor(x)
