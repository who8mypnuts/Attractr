#version 330
in float v_depth;
in float v_cv;
in float v_w;
uniform int u_mode;   // 0 = additive (count, depth·w, cv·w) into the accumulation FBO, 1 = depth into the zmin FBO (MIN blend)
out vec4 o_out;
void main() {
    if (u_mode == 0) {
        o_out = vec4(v_w, v_w * v_depth, v_w * v_cv, 0.0);
    } else {
        o_out = vec4(v_depth, 0.0, 0.0, 0.0);
    }
}
