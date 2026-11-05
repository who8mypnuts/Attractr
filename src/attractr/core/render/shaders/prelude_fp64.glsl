// ── Double-precision math for GLSL (GL_ARB_gpu_shader_fp64 gives arithmetic, sqrt, abs,
// floor, fract, mod… but NO transcendental functions).  Each routine uses a careful range
// reduction followed by a short polynomial; accuracy ≈ 1–2 ulp on the tested ranges
// (see tests/engines/test_fp64_math.py).

const double D_PI = 3.14159265358979323846LF;
const double D_HALF_PI = 1.57079632679489661923LF;
const double D_TWO_OVER_PI = 0.63661977236758134308LF;
// Cody–Waite split of π/2 for exact reduction
const double D_PIO2_1 = 1.57079632673412561417LF;
const double D_PIO2_2 = 6.07710050650619224932e-11LF;
const double D_PIO2_3 = 2.02226624879595063154e-21LF;
const double D_LN2 = 0.69314718055994530942LF;
const double D_LN2_HI = 0.69314718036912381649LF;
const double D_LN2_LO = 1.90821492927058770002e-10LF;

double _sincos_poly_sin(double r) {   // |r| <= π/4
    double r2 = r * r;
    return r * (1.0LF + r2 * (-1.0LF / 6.0LF + r2 * (1.0LF / 120.0LF + r2 * (-1.0LF / 5040.0LF
         + r2 * (1.0LF / 362880.0LF + r2 * (-1.0LF / 39916800.0LF + r2 * (1.0LF / 6227020800.0LF
         + r2 * (-1.0LF / 1307674368000.0LF))))))));
}
double _sincos_poly_cos(double r) {
    double r2 = r * r;
    return 1.0LF + r2 * (-0.5LF + r2 * (1.0LF / 24.0LF + r2 * (-1.0LF / 720.0LF + r2 * (1.0LF / 40320.0LF
         + r2 * (-1.0LF / 3628800.0LF + r2 * (1.0LF / 479001600.0LF + r2 * (-1.0LF / 87178291200.0LF)))))));
}
int _reduce_pio2(double x, out double r) {
    double k = floor(x * D_TWO_OVER_PI + 0.5LF);
    r = ((x - k * D_PIO2_1) - k * D_PIO2_2) - k * D_PIO2_3;
    return int(k) & 3;
}
double _sin(double x) {
    if (abs(x) > 1.0e9LF) return 0.0LF;
    double r; int q = _reduce_pio2(x, r);
    double s = (q == 0 || q == 2) ? _sincos_poly_sin(r) : _sincos_poly_cos(r);
    return (q >= 2) ? -s : s;
}
double _cos(double x) {
    if (abs(x) > 1.0e9LF) return 1.0LF;
    double r; int q = _reduce_pio2(x, r);
    double c = (q == 0 || q == 2) ? _sincos_poly_cos(r) : -_sincos_poly_sin(r);
    return (q >= 2) ? -c : c;
}
double _tan(double x) { double c = _cos(x); return abs(c) < 1e-300LF ? 1e300LF : _sin(x) / c; }

double _exp(double x) {
    x = clamp(x, -700.0LF, 700.0LF);
    double k = floor(x / D_LN2 + 0.5LF);
    double r = (x - k * D_LN2_HI) - k * D_LN2_LO;
    // Taylor to 1e-17 on |r| <= ln2/2
    double p = 1.0LF + r * (1.0LF + r * (1.0LF / 2.0LF + r * (1.0LF / 6.0LF + r * (1.0LF / 24.0LF + r * (1.0LF / 120.0LF
             + r * (1.0LF / 720.0LF + r * (1.0LF / 5040.0LF + r * (1.0LF / 40320.0LF + r * (1.0LF / 362880.0LF
             + r * (1.0LF / 3628800.0LF + r * (1.0LF / 39916800.0LF + r * (1.0LF / 479001600.0LF))))))))))));
    return ldexp(p, int(k));
}
double _logp(double x) {   // x > 0
    int e;
    double m = frexp(x, e);            // m in [0.5, 1)
    if (m < 0.70710678118654752LF) { m *= 2.0LF; e -= 1; }
    double f = (m - 1.0LF) / (m + 1.0LF);   // |f| <= 0.172
    double f2 = f * f;
    double s = f * (2.0LF + f2 * (2.0LF / 3.0LF + f2 * (2.0LF / 5.0LF + f2 * (2.0LF / 7.0LF + f2 * (2.0LF / 9.0LF
             + f2 * (2.0LF / 11.0LF + f2 * (2.0LF / 13.0LF + f2 * (2.0LF / 15.0LF + f2 * (2.0LF / 17.0LF + f2 * (2.0LF / 19.0LF))))))))));
    return s + double(e) * D_LN2;
}
double _powp(double a, double b) { return _exp(b * _logp(a)); }   // a > 0
double _atan_core(double x) {   // |x| <= 1
    // two half-angle reductions bring |x| below ~0.27 where the series converges fast
    x = x / (1.0LF + sqrt(1.0LF + x * x));
    x = x / (1.0LF + sqrt(1.0LF + x * x));
    double x2 = x * x;
    double s = x * (1.0LF + x2 * (-1.0LF / 3.0LF + x2 * (1.0LF / 5.0LF + x2 * (-1.0LF / 7.0LF + x2 * (1.0LF / 9.0LF
             + x2 * (-1.0LF / 11.0LF + x2 * (1.0LF / 13.0LF + x2 * (-1.0LF / 15.0LF + x2 * (1.0LF / 17.0LF + x2 * (-1.0LF / 19.0LF))))))))));
    return 4.0LF * s;
}
double _atan(double x) {
    double a = abs(x);
    double r = (a > 1.0LF) ? D_HALF_PI - _atan_core(1.0LF / a) : _atan_core(a);
    return x < 0.0LF ? -r : r;
}
double _atan2(double y, double x) {
    if (x == 0.0LF) return y > 0.0LF ? D_HALF_PI : (y < 0.0LF ? -D_HALF_PI : 0.0LF);
    double r = _atan(y / x);
    if (x < 0.0LF) r += (y >= 0.0LF) ? D_PI : -D_PI;
    return r;
}
double _asin(double x) { x = clamp(x, -1.0LF, 1.0LF); return _atan2(x, sqrt(1.0LF - x * x)); }
double _acos(double x) { return D_HALF_PI - _asin(x); }
double _sinh(double x) { double e = _exp(x); return 0.5LF * (e - 1.0LF / e); }
double _cosh(double x) { double e = _exp(x); return 0.5LF * (e + 1.0LF / e); }
double _tanh(double x) { if (abs(x) > 20.0LF) return sign(x); double e = _exp(2.0LF * x); return (e - 1.0LF) / (e + 1.0LF); }
double _asinh(double x) { return sign(x) * _logp(abs(x) + sqrt(x * x + 1.0LF)); }
double _acosh(double x) { x = max(x, 1.0LF); return _logp(x + sqrt(x * x - 1.0LF)); }
double _atanh(double x) { x = clamp(x, -0.999999999LF, 0.999999999LF); return 0.5LF * _logp((1.0LF + x) / (1.0LF - x)); }
