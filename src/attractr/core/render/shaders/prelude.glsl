// ── Attractr GLSL runtime prelude — mirrors core/formula/runtime_numba.py ──────────
// Requires the precision header (real / real3 / R() macros) to be defined before it.
// All transcendental functions go through _name() wrappers so the fp64 build can swap in
// the software double implementations from prelude_fp64.glsl.

uint _xorshift(inout uint s) {
    s ^= s << 13u; s ^= s >> 17u; s ^= s << 5u;
    return s;
}
real _rand(inout uint s) { return R(float(_xorshift(s) >> 8u) * (1.0 / 16777216.0)); }

#ifndef ATTRACTR_FP64
real _sin(real x)   { return sin(x); }
real _cos(real x)   { return cos(x); }
real _tan(real x)   { return tan(x); }
real _asin(real x)  { return asin(clamp(x, -1.0, 1.0)); }
real _acos(real x)  { return acos(clamp(x, -1.0, 1.0)); }
real _atan(real x)  { return atan(x); }
real _atan2(real y, real x) { return atan(y, x); }
real _sinh(real x)  { return sinh(x); }
real _cosh(real x)  { return cosh(x); }
real _tanh(real x)  { return tanh(x); }
real _asinh(real x) { return asinh(x); }
real _acosh(real x) { return acosh(max(x, 1.0)); }
real _atanh(real x) { return atanh(clamp(x, -0.999999, 0.999999)); }
real _exp(real x)   { return exp(min(x, 88.0)); }
real _logp(real x)  { return log(x); }   // x > 0
real _powp(real a, real b) { return pow(a, b); }   // a > 0
#endif

real _log(real x)   { real a = abs(x); return a < R(1e-30) ? R(-69.0) : _logp(a); }
real _log2(real x)  { return _log(x) * R(1.4426950408889634); }
real _log10(real x) { return _log(x) * R(0.4342944819032518); }
real _sqrt(real x)  { return sqrt(abs(x)); }
real _cbrt(real x)  { return x == R(0.0) ? R(0.0) : sign(x) * _powp(abs(x), R(1.0 / 3.0)); }
real _round(real x) { return floor(x + R(0.5)); }
real _pow(real a, real b) {
    if (a == R(0.0)) return R(0.0);
    real m = _powp(abs(a), b);
    return (a < R(0.0) && fract(b * R(0.5)) > R(0.25)) ? -m : m;
}
real _ipow2(real a) { return a * a; }
real _ipow3(real a) { return a * a * a; }
real _ipow4(real a) { real b = a * a; return b * b; }
real _hypot(real a, real b) { return sqrt(a * a + b * b); }
real _mod(real a, real b) { return b == R(0.0) ? R(0.0) : a - b * floor(a / b); }
real _randn(inout uint s) {
    real u1 = max(_rand(s), R(1e-12));
    real u2 = _rand(s);
    return sqrt(R(-2.0) * _logp(u1)) * _cos(R(6.283185307179586) * u2);
}
real _re_pow(real x, real y, real n) {
    int k = int(n); real rr = R(1.0), ri = R(0.0), bx = x, by = y;
    while (k > 0) {
        if ((k & 1) != 0) { real t = rr * bx - ri * by; ri = rr * by + ri * bx; rr = t; }
        real t2 = bx * bx - by * by; by = R(2.0) * bx * by; bx = t2; k >>= 1;
    }
    return rr;
}
real _im_pow(real x, real y, real n) {
    int k = int(n); real rr = R(1.0), ri = R(0.0), bx = x, by = y;
    while (k > 0) {
        if ((k & 1) != 0) { real t = rr * bx - ri * by; ri = rr * by + ri * bx; rr = t; }
        real t2 = bx * bx - by * by; by = R(2.0) * bx * by; bx = t2; k >>= 1;
    }
    return ri;
}
