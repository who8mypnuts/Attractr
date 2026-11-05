#version 330
//__PRECISION__
// ── GL 3.3 fallback: one vertex per trajectory, scattered into the accumulation FBO ──
uniform sampler2D u_state;
uniform sampler2D u_old;
uniform int   u_tex_w;
uniform mat3  u_R;
uniform vec3  u_center;
uniform float u_inv_radius;
uniform vec2  u_c;
uniform float u_focal;
uniform float u_persp;
uniform vec2  u_size;       // accumulation buffer size in pixels
uniform int   u_color_code;
uniform float u_inv_n;
uniform int   u_line;       // 1 = emit the segment end points (gap filling) instead of a point
uniform float u_p[__NPARAMS__];

out float v_depth;
out float v_cv;
out float v_w;

//__PRELUDE__
//__STEP__

float color_value(float qx, float qy, float qz, float speed, float radius, float idx, vec4 s) {
    switch (u_color_code) {
        case 1: return qx;  case 2: return qy;  case 3: return qz;  case 4: return qz;
        case 5: return speed; case 6: return radius; case 7: return idx; case 8: return 0.5;
        case 9: return color_fn(s.x, s.y, s.z, s.w);
    }
    return 0.0;
}

vec3 plotted(vec4 s) {
#if HAS_PLOT
    real px, py, pz;
    plot_fn(s.x, s.y, s.z, s.w, px, py, pz);
    return vec3(px, py, pz);
#else
    return s.xyz;
#endif
}

void main() {
    int id = u_line != 0 ? gl_VertexID / 2 : gl_VertexID;
    ivec2 tc = ivec2(id % u_tex_w, id / u_tex_w);
    vec4 s = texelFetch(u_state, tc, 0);
    vec4 o = texelFetch(u_old, tc, 0);
    bool restarted = o.x > 1e29;
#if HAS_SECTION
    float sv_new = section_fn(s.x, s.y, s.z, s.w);
    bool crossed = !restarted && section_fn(o.x, o.y, o.z, o.w) * sv_new < 0.0
                   && (SECTION_DIR == 0 || (SECTION_DIR == 1 && sv_new > 0.0) || (SECTION_DIR == 2 && sv_new < 0.0));
    if (!crossed) {
        gl_Position = vec4(-10.0, -10.0, 0.0, 1.0);   // no section crossing this step
        return;
    }
#endif
    vec3 ps = plotted(s);
    vec3 po = restarted ? ps : plotted(o);
    vec3 p = (u_line != 0 && (gl_VertexID & 1) == 0) ? po : ps;
    vec3 q = u_R * ((p - u_center) * u_inv_radius);
    float d = max(1.0 + u_persp * q.z, 0.05);
    float u = u_c.x + u_focal * q.x / d;
    float v = u_c.y - u_focal * q.y / d;
    vec3 qs = u_R * ((ps - u_center) * u_inv_radius);
    vec3 qo = u_R * ((po - u_center) * u_inv_radius);
    float speed = length(s.xyz - o.xyz) * u_inv_radius;
    v_cv = color_value(qs.x, qs.y, qs.z, speed, length(qs), float(id) * u_inv_n, s);
    v_depth = q.z;
    v_w = 1.0;
    if (u_line != 0) {
        // weight per rasterised pixel ≈ 1 / segment length so density stays ∝ time spent
        float du = max(1.0 + u_persp * qo.z, 0.05);
        vec2 uo = vec2(u_c.x + u_focal * qo.x / du, u_c.y - u_focal * qo.y / du);
        float ds = max(1.0 + u_persp * qs.z, 0.05);
        vec2 us = vec2(u_c.x + u_focal * qs.x / ds, u_c.y - u_focal * qs.y / ds);
        float len = distance(uo, us);
        v_w = 1.0 / max(len, 1.0);
        if (len > u_size.x + u_size.y || restarted) { gl_Position = vec4(-10.0, -10.0, 0.0, 1.0); return; }
    } else if (restarted) {
        gl_Position = vec4(-10.0, -10.0, 0.0, 1.0);   // just restarted: do not plot
        return;
    }
    gl_Position = vec4((u + 0.5) / u_size.x * 2.0 - 1.0, (v + 0.5) / u_size.y * 2.0 - 1.0, 0.0, 1.0);
    gl_PointSize = 1.0;
}
