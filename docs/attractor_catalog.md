# Attractor Catalogue

Every attractor Attractr will ship with, its equations, parameters and defaults, and
where it came from. Equations are written in the Attractr formula DSL (see
[formula_dsl.md](formula_dsl.md)) because **the built-in attractors are themselves DSL
files** — the same text generates the CPU (numba) code, the GPU (GLSL) code, the formula
shown in the Info panel and this documentation page.

Kinds:

* **map** — discrete iteration `x' = f(x)`; every step produces one point.
* **flow** — ODE `dx/dt = f(x)`; integrated with RK4 (default) or Euler; `dt` is an
  integrator setting (default per system), not a shape parameter.
* **ifs** — random choice between several affine/other maps (probabilities).
* **special** — needs a custom step (randomness + branches) but is still expressible in
  the DSL via `rand()` / `select()`.

Sources: **A** = chaoscope_original (Android/C++), **C** = chaoscope_rewrite (C),
**W** = strange-attractors-webgl, **K** = classic Chaoscope feature set, **N** = new.

Tier 1 = everything present in the three sources (must ship in Milestone 1).
Tier 2 = additions (Milestone 6 unless trivial).

---

## 1. Maps (2-D and 3-D)

| Name | Src | Tier | Equations | Params (defaults) · ranges |
|---|---|---|---|---|
| Clifford | A W | 1 | `x' = sin(a*y) + c*cos(a*x)` `y' = sin(b*x) + d*cos(b*y)` `z' = sin(e*y) + f*cos(e*z)` | a=-1.4 b=1.6 c=1.0 d=0.7 e=1.5 f=0.5 · all [-3,3]. 2-D when e=f=0 (flag `flat`). **Canonical form — the WebGL source's `sin(c*x)` is a bug.** |
| Peter de Jong | A W | 1 | `x' = sin(a*y) - cos(b*x)` `y' = sin(c*x) - cos(d*y)` `z' = sin(e*z) - cos(f*y)` | a=-2.0 b=-2.0 c=-1.2 d=2.0 e=1.8 f=-1.5 · [-3,3] |
| Pickover | A K | 1 | `x' = sin(a*y) - z*cos(b*x)` `y' = z*sin(c*x) - cos(d*y)` `z' = sin(x)` | a=2.24 b=0.43 c=-0.65 d=-2.43 · [-3,3] |
| Gumowski–Mira | A | 1 | `f(x) = mu*x + 2*(1-mu)*x^2/(1+x^2)` `x' = y + a*(1-0.05*y^2)*y + f(x)` `y' = -x + f(x')` | a=0.008 mu=-0.496 · [-1,1] |
| Hénon | A | 1 | `x' = 1 - a*x^2 + y` `y' = b*x` | a=1.4 b=0.3 · a[1,1.42] b[0.1,0.35] |
| Bedhead | W | 1 | `x' = sin(x*y/b) + cos(a*x - y)` `y' = x + sin(y)/b` | a=-0.81 b=-0.92 · [-1,1] |
| Fractal Dream (Latoocarfian) | W | 1 | `x' = sin(b*y) + c*sin(b*x)` `y' = sin(a*x) + d*sin(a*y)` | a=-0.966918 b=2.879879 c=0.765145 d=0.744728 · a,b[-3,3] c,d[-1.5,1.5] |
| Symmetric Icon (general) | A K | 1 | `zz = x^2+y^2`; `re_n, im_n = Re/Im(z^n)`; `t = lam + al*zz + be*re_n + om*i` `z' = t*z + ga*conj(z)^(n-1)` (real form expanded by codegen) `depth = re_n` | lam=-2.5 al=5.0 be=-1.8 ga=1.0 om=0.0 n=3 (int 3–12) — Android's p=3 icon is the special case om=0 |
| Tinkerbell | N | 2 | `x' = x^2 - y^2 + a*x + b*y` `y' = 2*x*y + c*x + d*y` | a=0.9 b=-0.6013 c=2.0 d=0.5 |
| Ikeda | N | 2 | `t = c - d/(1+x^2+y^2)` `x' = a + b*(x*cos(t) - y*sin(t))` `y' = b*(x*sin(t) + y*cos(t))` | a=1 b=0.9 c=0.4 d=6 |
| Hopalong (Martin) | N | 2 | `x' = y - sign(x)*sqrt(abs(b*x - c))` `y' = a - x` | a=2.0 b=1.0 c=0.0 |
| Svensson | N | 2 | `x' = d*sin(a*x) - sin(b*y)` `y' = c*cos(a*x) + cos(b*y)` | a=1.4 b=1.56 c=1.4 d=-6.56 |
| Duffing map | N | 2 | `x' = y` `y' = -b*x + a*y - y^3` | a=2.75 b=0.2 |
| Lozi | N | 2 | `x' = 1 - a*abs(x) + y` `y' = b*x` | a=1.7 b=0.5 |
| Gingerbreadman | N | 2 | `x' = 1 - y + abs(x)` `y' = x` | — |
| Popcorn (Pickover) | N | 2 | `x' = x - h*sin(y + tan(k*y))` `y' = y - h*sin(x + tan(k*x))` | h=0.05 k=3 (many random starts) |
| Kaplan–Yorke | N | 2 | `x' = mod(2*x, 1)` `y' = al*y + cos(4*pi*x)` | al=0.2 |
| Bogdanov | N | 2 | `yn = y + eps*y + k*x*(x-1) + mu*x*y` `x' = x + yn` `y' = yn` | eps=0 k=1.2 mu=0 |
| Chirikov standard map | N | 2 | `p' = mod(p + K*sin(x), 2*pi)` `x' = mod(x + p', 2*pi)` | K=0.971635 |
| Polynomial A (Chaoscope) | K | 2 | `x' = a0 + y - y*z` `y' = a1 + z - x*z` `z' = a2 + x - x*y` | a0..a2 (to be verified against classic) |
| Polynomial B (Chaoscope) | K | 2 | `x' = a0 + y - z*(a1 + y)` `y' = a2 + z - x*(a3 + z)` `z' = a4 + x - y*(a5 + x)` | a0..a5 (to be verified) |
| Polynomial Sprott (quadratic 3-D) | K N | 2 | each of x',y',z' = `c0 + c1 x + c2 y + c3 z + c4 x² + c5 y² + c6 z² + c7 xy + c8 xz + c9 yz` | 30 coefficients in [-1.2,1.2]; primary target of **Search** |
| Cubic 3-D map | N | 2 | as above with cubic monomials (60 coeffs) | Search target |

## 2. Flows (ODE systems)

dt = default integration step (RK4). IC = nominal initial condition (jittered per
trajectory).

| Name | Src | Tier | Equations | Params (defaults) | dt · IC |
|---|---|---|---|---|---|
| Lorenz | A C K | 1 | `dx = sigma*(y-x)` `dy = x*(rho-z) - y` `dz = x*y - beta*z` | sigma=10 rho=28 beta=8/3 | 0.005 · (0.1,0,0) |
| Rössler | A C | 1 | `dx = -(y+z)` `dy = x + a*y` `dz = b + z*(x-c)` | a=0.2 b=0.2 c=5.7 | 0.02 |
| Aizawa | A C | 1 | `dx = (z-b)*x - d*y` `dy = d*x + (z-b)*y` `dz = c + a*z - z^3/3 - (x^2+y^2)*(1+e*z) + f*z*x^3` | a=0.95 b=0.7 c=0.6 d=3.5 e=0.25 f=0.1 | 0.01 |
| Thomas | A C | 1 | `dx = sin(y) - b*x` `dy = sin(z) - b*y` `dz = sin(x) - b*z` | b=0.208186 | 0.05 |
| Halvorsen | A C | 1 | `dx = -a*x - 4*y - 4*z - y^2` (cyclic) | a=1.4 (preset "Pretzel" a=1.89) | 0.005 · (-5,0,0) |
| Dadras (Chaotic Flow) | A C | 1 | `dx = y - a*x + b*y*z` `dy = c*y - x*z + z` `dz = d*x*y - e*z` | a=3 b=2.7 c=1.7 d=2 e=9 | 0.005 · (1.1,2.1,-2) |
| Burke–Shaw | A C | 1 | `dx = -s*(x+y)` `dy = -y - s*x*z` `dz = s*x*y + v` | s=10 v=4.272 | 0.005 · (0.6,0.5,0.5) |
| Lorenz-84 (Hadley) | A C | 1 | `dx = -y^2 - z^2 - a*x + a*F` `dy = x*y - b*x*z - y + G` `dz = b*x*y + x*z - z` | a=0.25 b=4 F=8 G=1 | 0.01 |
| Chen | C | 1 | `dx = a*(y-x)` `dy = (c-a)*x - x*z + c*y` `dz = x*y - b*z` | a=35 b=3 c=28 | 0.005 |
| Lü | C | 1 | `dx = a*(y-x)` `dy = -x*z + c*y` `dz = x*y - b*z` | a=36 b=3 c=20 | 0.005 |
| Rucklidge | C | 1 | `dx = -kappa*x + lambda*y - y*z` `dy = x` `dz = -z + y^2` | kappa=2 lambda=6.7 | 0.01 · (1,0,4.5) |
| Four-wing | C | 1 | `dx = a*x + c*y*z` `dy = b*x + d*y - x*z` `dz = e*z + f*x*y` | a=0.2 b=-0.01 c=1 d=-0.4 e=-1 f=-1 | 0.05 · (1,1,1) |
| Sprott A (Nosé–Hoover) | C | 1 | `dx = y` `dy = -x + y*z` `dz = 1 - y^2` | — | 0.02 · (0,5,0) |
| Sprott B | A C | 1 | `dx = a*y*z` `dy = x - y` `dz = 1 - b*x*y` | a=1 b=1 (C: fixed 1) | 0.02 |
| Sprott C | C | 1 | `dx = y*z` `dy = x - y` `dz = 1 - x^2` | — | 0.02 |
| Sprott D | C | 1 | `dx = -y` `dy = x + z` `dz = x*z + 3*y^2` | — | 0.02 · (0.11,0.08,0.14) |
| Sprott E | C | 1 | `dx = y*z` `dy = x^2 - y` `dz = 1 - 4*x` | — | 0.02 |
| Sprott F | C | 1 | `dx = y + z` `dy = -x + a*y` `dz = x^2 - b*z` | a=0.5 b=1 | 0.02 |
| Sprott G | C | 1 | `dx = a*x + b*z` `dy = x*z - y` `dz = -x + y` | a=0.4 b=1 | 0.02 |
| Sprott H | C | 1 | `dx = -y + z^2` `dy = x + a*y` `dz = x - b*z` | a=0.5 b=1 | 0.02 |
| Sprott I | C | 1 | `dx = -a*y` `dy = x + z` `dz = x + y^2 - b*z` | a=0.2 b=1 | 0.02 |
| Sprott J | C | 1 | `dx = a*z` `dy = -b*y + z` `dz = -x + y + y^2` | a=2 b=2 | 0.02 |
| Sprott K | C | 1 | `dx = x*y - z` `dy = x - y` `dz = a*x + b*z` | a=1 b=0.3 | 0.02 |
| Sprott L | C | 1 | `dx = y + a*z` `dy = 0.9*x^2 - y` `dz = b - x` | a=3.9 b=1 | 0.02 |
| Sprott M | C | 1 | `dx = -z` `dy = -x^2 - y` `dz = a + b*x + y` | a=1.7 b=1.7 | 0.02 |
| Sprott N | C | 1 | `dx = -a*y` `dy = x + z^2` `dz = 1 + y - b*z` | a=2 b=2 | 0.02 |
| Sprott O | C | 1 | `dx = y` `dy = x - z` `dz = a*x + x*z + b*y` | a=1 b=2.7 | 0.02 · (-0.19,0.24,-0.12) |
| Sprott P | C | 1 | `dx = a*y + z` `dy = -x + y^2` `dz = x + b*y` | a=2.7 b=1 | 0.02 |
| Sprott Q | C | 1 | `dx = -z` `dy = x - y` `dz = a*x + y^2 + b*z` | a=3.1 b=0.5 | 0.02 |
| Sprott R | C | 1 | `dx = a - y` `dy = b + z` `dz = x*y - z` | a=0.9 b=0.4 | 0.02 |
| Sprott S | C | 1 | `dx = -x - a*y` `dy = x + z^2` `dz = b + x` | a=4 b=1 | 0.02 |
| Arneodo | C | 1 | `dx = y` `dy = z` `dz = -a*x - b*y - c*z + d*x^3` | a=-5.5 b=3.5 c=1 d=-1 | 0.02 |
| Coullet | C | 1 | same as Arneodo | a=-0.8 b=1.1 c=0.45 d=-1 | 0.02 |
| Lorenz mod 2 | C | 1 | `dx = -a*x + y^2 - z^2 + a*c` `dy = x*(y - b*z) + d` `dz = -z + x*(b*y + z)` | a=0.9 b=5 c=9.9 d=1 | 0.01 |
| Chua | C | 1 | `h = m1*x + 0.5*(m0-m1)*(abs(x+1) - abs(x-1))` `dx = alpha*(y - x - h)` `dy = x - y + z` `dz = -beta*y` | alpha=15.6 beta=28 m0=-8/7 m1=-5/7 | 0.005 · (0.7,0,0) |
| Chen–Lee | C | 1 | `dx = a*x - y*z` `dy = b*y + x*z` `dz = c*z + x*y/3` | a=5 b=-10 c=-3.8 | 0.01 |
| Dequan Li | C | 1 | `dx = a*(y-x) + d*x*z` `dy = k*x + f*y - x*z` `dz = c*z + x*y - eps*x^2` | a=40 c=11/6 d=0.16 eps=0.65 k=55 f=20 | 0.0005 · (0.349,0,-0.16) |
| Three-scroll unified | C | 1 | `dx = a*(y-x) + d*x*z` `dy = c*y - x*z` `dz = b*z + x*y - e*x^2` | a=40 b=0.833 c=20 d=0.5 e=0.65 | 0.0005 |
| Finance | C | 1 | `dx = (1/b - a)*x + z + x*y` `dy = -b*y - x^2` `dz = -x - c*z` | a=3 b=0.1 c=1 | 0.01 · (1,-8,0.5) |
| Rabinovich–Fabrikant | C | 1 | `dx = y*(z - 1 + x^2) + gamma*x` `dy = x*(3*z + 1 - x^2) + gamma*y` `dz = -2*z*(alpha + x*y)` | alpha=0.14 gamma=0.10 | 0.01 · (-1,0,0.5) |
| Newton–Leipnik | C | 1 | `dx = -alpha*x + y + 10*y*z` `dy = -x - 0.4*y + 5*x*z` `dz = beta*z - 5*x*y` | alpha=0.4 beta=0.175 | 0.01 · (0.349,0,-0.16) |
| Rikitake | C | 1 | `dx = -mu*x + y*z` `dy = -mu*y + (z-a)*x` `dz = 1 - x*y` | mu=2 a=5 | 0.02 |
| Genesio–Tesi | N | 2 | `dx = y` `dy = z` `dz = -c*x - b*y - a*z + x^2` | a=0.44 b=1.1 c=1 | 0.01 |
| Shimizu–Morioka | N | 2 | `dx = y` `dy = x - a*y - x*z` `dz = -b*z + x^2` | a=0.75 b=0.45 | 0.01 |
| Sakarya | N | 2 | `dx = -x + y + y*z` `dy = -x - y + a*x*z` `dz = z - b*x*y` | a=0.4 b=0.3 | 0.01 |
| Bouali | N | 2 | `dx = x*(4-y) + a*z` `dy = -y*(1-x^2)` `dz = -x*(1.5 - s*z) - 0.05*z` | a=0.3 s=1 | 0.005 |
| Yu–Wang | N | 2 | `dx = a*(y-x)` `dy = b*x - c*x*z` `dz = exp(x*y) - d*z` | a=10 b=40 c=2 d=2.5 | 0.002 |
| Qi–Chen | N | 2 | `dx = a*(y-x) + y*z` `dy = c*x + y - x*z` `dz = x*y - b*z` | a=38 b=8/3 c=80 | 0.001 |
| Liu | N | 2 | `dx = a*(y-x)` `dy = b*x - k*x*z` `dz = -c*z + h*x^2` | a=10 b=40 c=2.5 k=1 h=4 | 0.002 |
| Moore–Spiegel | N | 2 | `dx = y` `dy = z` `dz = -z - (T - R + R*x^2)*y - T*x` | T=6 R=20 | 0.01 |
| Duffing oscillator (forced) | N | 2 | state (x,y,t): `dx = y` `dy = x - x^3 - delta*y + gamma*cos(omega*t)` `dt = 1`; plot (x,y,t mod period) | delta=0.3 gamma=0.5 omega=1.2 | 0.02 |

## 3. Random / special systems

| Name | Src | Tier | Definition | Params |
|---|---|---|---|---|
| IFS (general) | A K | 1 | N maps, each `(x,y,z) → A·(x,y,z) + t` with probability p_i; DSL `choose { p: ... }` | editable table; presets: Barnsley fern (2-D and 3-D twist variant `width, lean, twist`), Sierpinski tetrahedron, Menger dust, Dragon, Spiral |
| Julia (quaternion, inverse iteration) | A K | 1 | `q' = ±sqrt(q - c)` in the k = 0 slice; random branch | c_re=-0.2 c_im=0.6 c_j=0.3 · [-2,2]² × [-1,1] |
| Julia (complex 2-D) | N | 2 | special case c_j = 0 (kept as separate entry for discoverability) | c_re=-0.7 c_im=0.27 |
| Orbit Trace (animation mode) | A | 1 | not an attractor — single ordered trajectory drawn incrementally | — |

## 3b. Library extensions (Tier 3 — added after the plan, see `suggested-improvements.md`)

All verified with the Lyapunov probe at their defaults (λ₁ > 0 unless noted). Sources: **S** =
suggested-improvements list, **L** = literature.

### Maps

| Name | Src | Equations | Params (defaults) | Notes |
|---|---|---|---|---|
| Zaslavskii web map | S L | `mu = (1-exp(-r))/r` `x' = mod(x + v*(1+mu*y) + eps*v*mu*cos(2*pi*x), 1)` `y' = exp(-r)*(y + eps*cos(2*pi*x))` `plot = x, y*yscale, 0` | v=133.33 r=3 eps=0.3 yscale=20 | y is squeezed by e⁻ʳ, hence the plot stretch |
| Cathala | S | `x' = a*x + y` `y' = b + x^2` | a=0.7 b=-0.82 | |
| Quadrup-Two (Martin) | S L | `x' = y - sign(x)*sin(log(abs(b*x-c)))*atan(log(abs(c*x-b))^2)` `y' = a - x` | a=34 b=1 c=5 | |
| Threeply (Martin) | S L | `x' = y - sign(x)*abs(sin(x)*cos(b) + c - x*sin(a+b+c))` `y' = a - x` | a=-55 b=-1 c=-42 | large extent (~10³) |
| Ushiki | S L | `x' = (a - x - b*y)*x` `y' = (c - y - d*x)*y` | a=3.7 b=0.1 c=3.5 d=0.15 | |
| Gumowski–Mira (extended) | S | as GM with `b` exposed and `f(x)` = mix(rational, exponential, s) | a=0.008 b=0.05 mu=-0.7 s=0 | |
| Symmetric Icon (extended) | S L | icon + `de*Re((z/|z|)^(n*p))*|z|` term | λ=-2.08 α=1 β=-0.1 γ=0.167 δ=0 ω=0 n=7 p=1 | 8 curated presets from *Symmetry in Chaos* |
| Chaos game (n-gon with rules) | S L | `k` = random vertex, re-drawn when forbidden by `avoid` (uses `w` as memory) `x' = x + (cos(2πk/n + twist) - x)*s` … `w' = k` | n=5 s=0.5 avoid=1 twist=0 | restricted chaos game; presets: pentagon/hexagon/square/Sierpinski/spiral |
| Lorenz (Poincaré section) | S | Lorenz + `plot = x, y, 0` `section = z - height` | height=27, `boost: 40` | the "Lorenz map" |
| Rössler (Poincaré section) | S | Rössler + `plot = x, z, 0` `section = y` | `boost: 150` | both crossing directions are kept |

Dropped after testing: *Burning Ship orbit cloud* (escape-time iteration has no bounded
attractor — framing is dominated by escaping orbits), *Duffing–van der Pol map* (no chaotic
parameter set found in a quick search), *Hadley* (identical to Lorenz-84 → curated preset
"Hadley spring" instead), *Langford* (identical to Aizawa).

### Flows

| Name | Src | Equations | Params (defaults) | dt · IC |
|---|---|---|---|---|
| Nosé–Hoover | S L | `dx = y` `dy = -x + y*z` `dz = a - y^2` | a=1.5 | 0.02 · (0,5,0); conservative |
| Wei (no equilibrium) | S L | `dx = -y` `dy = x + z` `dz = 2*y^2 + x*z - a` | a=0.35 | 0.005 · (0.5,0.5,0) jitter 0.05 — small basin |
| Thomas (asymmetric) | S | `dx = sin(y) - b1*x` `dy = sin(z) - b2*y` `dz = sin(x) - b3*z` | b=(0.132, 0.093, 0.172) | 0.05; values found by a random λ₁ scan (most asymmetric triples are quasi-periodic) |
| Wang–Sun | S L | `dx = a*x + c*y*z` `dy = b*x + d*y - x*z` `dz = e*z + f*x*y` | a=0.2 b=-0.01 c=1 d=-0.4 e=-1 f=-1 | 0.02 |
| Anishchenko–Astakhov | S L | `dx = m*x + y - x*z` `dy = -x` `dz = -g*z + g*step(0,x)*x^2` | m=1.2 g=0.5 | 0.02 |
| Linz–Sprott jerk | S L | `dz = -a*z - y + abs(x) - 1` | a=0.6 | 0.02 |
| Sprott simplest quadratic jerk | S L | `dz = -a*z + y^2 - x` | a=2.017 | 0.02 · (-0.5,0,0) jitter 0.05 — small basin |
| Sprott cubic jerk | S L | `dz = -a*z + x*y^2 - x` | a=2.028 | 0.02 · (0.5,0,0) jitter 0.02 — small basin |
| Malasoma jerk | S L | `dz = -a*z + x*y - x` | a=2.05 | 0.02 · (1,0,0) jitter 0.02 — weakly chaotic (λ₁ ≈ 0.02) |
| Duffing (driven) | S L | `dx = y` `dy = x - x^3 - delta*y + gamma*cos(omega*w)` `dw = 1` `plot = x, y, 0` | δ=0.3 γ=0.5 ω=1.2 | 0.01 |
| Duffing (stroboscopic map) | S L | + `section = sin(omega*w/2 - phase*pi/360)` | + phase=0 | `boost: 300` |
| Ueda | S L | `dx = y` `dy = -k*y - x^3 + B*cos(w)` `dw = 1` | k=0.05 B=7.5 | 0.01 · (2.5,0,0) |
| Ueda (stroboscopic map) | S L | + `section = sin(w/2)` | | `boost: 300` |
| Van der Pol (driven) | S L | `dx = y` `dy = mu*(1-x^2)*y - x + A*cos(omega*w)` `dw = 1` `plot = x, y*yscale, 0` | μ=5 A=5 ω=2.463 yscale=0.25 | 0.005; Parlitz–Lauterborn chaotic case (the textbook μ=8.53, A=1.2, ω=2π/10 set is periodic at this dt) |
| Rössler hyperchaos (4-D) | S L | `dx = -y - z` `dy = x + a*y + w` `dz = b + x*z` `dw = -c*z + d*w` | a=0.25 b=3 c=0.5 d=0.05 | 0.005 · (-10,-6,0,10) |
| Lorenz–Stenflo (4-D) | S L | `dx = sigma*(y-x) + s*w` `dy = x*(r-z) - y` `dz = x*y - b*z` `dw = -x - sigma*w` | σ=1 r=26 b=0.7 s=1.5 | 0.005 · (1,1,1,1) |

### IFS

| Name | Maps | Params |
|---|---|---|
| Sierpinski carpet | 8 × ratio s | s=1/3 |
| Vicsek fractal | 5 × ratio s, edge or corner layout | s=1/3 corner=0 |
| Koch curve | 4 × ratio s, middle two rotated ±deg | s=1/3 deg=60 |
| Lévy C curve | 2 × ratio r rotated ±th | r=1/√2 th=45 |
| Pythagoras tree | 2 square-stacking maps + condensation map `x' = rand(); y' = rand()` (weight 0.3) | deg=45 |
| de Rham curve | `d0(z) = a z`, `d1(z) = a + (1-a) z` (optionally on conj z) | ar=0.5 ai=0.2887 conj=1; presets Koch / Peano / Lévy C / Cesàro |
| Maple leaf (Barnsley) | 4 affine maps (Bourke coefficients) | spread=1 |
| Fractal tree (Barnsley) | trunk + 2 rotated branches + bud | deg=45 shrink=0.6 |

## 4. Parameter metadata carried for every attractor

For each parameter: symbol, display name, default, soft range (slider), hard range
(validation), step/precision, **hint text** (from the Android strings, e.g. *"σ (Prandtl
number) — fluid viscosity. Standard value is 10."*), and `animatable: true`.
For each attractor: display name, family/kind, dimensionality (2-D/3-D), description
paragraph, references (paper / URL), default camera, default palette, curated presets
(ported from `CURATED_PRESETS`: 3 per Android attractor, plus the C rewrite defaults as
"Reference" presets), Lyapunov exponent at defaults (computed once, stored for the Info
panel), recommended iteration count tier.

## 5. Presets to port verbatim (from `AttractorDefs.kt`)

Clifford: Classic · Filigree · Ember — de Jong: Shells · Storm · Filament — Gumowski-Mira:
Jellyfish · Coral · Bloom — Lorenz: Butterfly · Side Wing · Storm Cell — Rössler: Spiral ·
Funnel · Pinball — Aizawa: Torus · Möbius · Coil — Thomas: Yarn Ball · Hyperchaos ·
Lattice — Dadras: Ribbon · Tempest · Mist — Icon: Mandala · Sunwheel · Snowflake — IFS:
Fern · Spiral · Broadleaf — Julia: Dragon · Bud · Bulb — Pickover: Wings · Conch · Veil —
Halvorsen: Pretzel · Knot · Coil — Burke-Shaw: Galaxy · Tornado · Whirlpool — Sprott-B:
Disc · Halo · Vortex — Lorenz-84: Climate · Jet · Monsoon — Hénon: Banana · Filament ·
Crescent. (Camera angles, palette and style per preset are in the Kotlin table and will be
transcribed into `resources/presets/curated.json`.)
