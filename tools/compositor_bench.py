#!/usr/bin/env python3
"""
VOP Diagnostic Tool:    compositor_bench.py
Description:            Standalone harness for the SINGLE-PASS compositor.
                        Renders test scenes twice: once through the engine's
                        current multi-pass path, once through a new one-draw
                        shader, then diffs the pixels and times both.

    sudo systemctl stop vop
    ./venv/bin/python tools/compositor_bench.py
    sudo systemctl start vop

    --headless      standalone EGL context instead of the KMSDRM display
    --save DIR      write old/new/diff PNGs for every scene
    --frames N      timed frames per row (default 60)
    --no-timing / --no-diff
"""
# (paste the AGPL licence comment block here)

import argparse
import math
import os
import sys
import time

# Same trick as the other tools/ scripts: make ../modules importable.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, 'modules'))

import numpy as np
import cv2
import moderngl

# The engine's REAL shader program and the REAL matrix builder.
import graphics_utils as gfx
import vop_math as vmath

# Field of view used by every test scene (degrees, vertical).
FOV = 45.0

# The backwards projection (python builds the matrix, see Rig.hinv):
#   A quad point is (vx, vy, 0, 1). The 4x4 MVP maps it to clip (x,y,z,w).
#   With z=0 the third column drops out, leaving a 3x3 matrix M3 mapping
#   (vx, vy, 1) -> (x, y, w). A screen pixel in NDC is (x/w, y/w), so
#   (vx, vy, 1) = w * inverse(M3) * (ndcx, ndcy, 1).
#   Let q = inverse(M3) * (ndcx, ndcy, 1). Then:
#       1/w   = q.z            (w = distance in front of the camera)
#       vx,vy = q.xy / q.z     (-1..+1 inside the quad)
#       texture coord = v * 0.5 + 0.5   (same as the old in_tex)
NEW_VERT = """
#version 300 es
layout (location = 0) in vec2 in_vert;
void main() {
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

NEW_FRAG = """
#version 300 es
// highp on purpose: the homography divide needs real 32-bit floats.
precision highp float;
precision highp int;
precision highp sampler2D;

uniform vec2 u_screen;                       // framebuffer size in pixels

uniform sampler2D tex_pm;                    // one image per layer,
uniform sampler2D tex_bp1;                   // bound ONCE per exposure
uniform sampler2D tex_bp2;

uniform mat3 h_pm;                           // inverse(M3) per layer
uniform mat3 h_bp1;
uniform mat3 h_bp2;

uniform int on_pm;                           // 1 = textured quad, 0 = hidden
uniform int on_bp1;
uniform int on_bp2;

uniform vec2 sweep_pm;                       // (mode 0..3, width)
uniform vec2 sweep_bp1;
uniform vec2 sweep_bp2;
uniform float sweep_pos;                     // shared smear clock

uniform bool mono_mode;
uniform vec3 gel;                            // PM gel (pg), as filter_color
uniform vec3 bg;                             // colour outside the PM quad

out vec4 f_color;

// 1/far and 1/near of vop_math's projection (near 0.1, far 1000).
// q.z = 1/w, and the GPU clips anything with w outside [near, far].
const float Z_MIN = 0.001;
const float Z_MAX = 10.0;

// Same maths as the old shader's sweep block, byte for byte.
vec3 sweep_filter(vec3 col, vec2 sw) {
    int mode = int(sw.x + 0.5);
    if (mode == 0) return col;
    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    float w = sw.y;
    float c = -w + sweep_pos * (1.0 + 2.0 * w);
    float above_lo = step(c - w, luma);
    float below_hi = 1.0 - step(c + w + 1e-6, luma);
    float lit;
    if (mode == 1)      lit = above_lo;
    else if (mode == 3) lit = below_hi;
    else                lit = above_lo * below_hi;
    return vec3(lit);
}

// Sweep first, then mono - the same order as the old shader.
vec3 shade(vec3 col, vec2 sw) {
    col = sweep_filter(col, sw);
    if (mono_mode) col = vec3(dot(col, vec3(0.299, 0.587, 0.114)));
    return col;
}

// Does this pixel land on the layer's quad? If so, fetch the colour.
bool hit_layer(sampler2D t, mat3 hinv, vec2 ndc, out vec3 rgb) {
    vec3 q = hinv * vec3(ndc, 1.0);
    // Behind the camera (q.z <= 0) or outside the near/far planes.
    if (q.z < Z_MIN || q.z > Z_MAX) return false;
    vec2 v = q.xy / q.z;
    // Outside the quad's -1..+1 footprint.
    if (abs(v.x) > 1.0 || abs(v.y) > 1.0) return false;
    // textureLod: no screen-space derivatives needed inside branches.
    // These textures have no mipmaps, so level 0 is what texture() used.
    rgb = textureLod(t, v * 0.5 + 0.5, 0.0).rgb;
    return true;
}

void main() {
    vec2 ndc = gl_FragCoord.xy / u_screen * 2.0 - 1.0;
    vec3 c;

    // ---- PM (the layer that used to draw straight to the screen) ----
    vec3 pm;
    if (on_pm == 0) {
        // Hidden PM: the old path still drew a full-screen WHITE quad and
        // still ran the sweep + mono + gel on it. Same here.
        pm = shade(vec3(1.0), sweep_pm) * gel;
    } else if (hit_layer(tex_pm, h_pm, ndc, c)) {
        pm = shade(c, sweep_pm) * gel;
    } else {
        pm = bg;
    }
    // Anything x 0 = 0, so if PM is black we can skip the two BP fetches.
    if (pm == vec3(0.0)) { f_color = vec4(0.0, 0.0, 0.0, 1.0); return; }

    // ---- BP1 (old path: FBO cleared black, quad drawn on top) ----
    // Hidden BP = 1.0 = identity under multiply, and NO sweep, because the
    // old path returned before set_sweep() for hidden bipack layers.
    vec3 bp1 = vec3(1.0);
    if (on_bp1 != 0) {
        bp1 = hit_layer(tex_bp1, h_bp1, ndc, c) ? shade(c, sweep_bp1) : vec3(0.0);
    }
    if (bp1 == vec3(0.0)) { f_color = vec4(0.0, 0.0, 0.0, 1.0); return; }

    // ---- BP2 ----
    vec3 bp2 = vec3(1.0);
    if (on_bp2 != 0) {
        bp2 = hit_layer(tex_bp2, h_bp2, ndc, c) ? shade(c, sweep_bp2) : vec3(0.0);
    }

    f_color = vec4(pm * bp1 * bp2, 1.0);
}
"""

def make_context(headless, size):
    """Return (ctx, width, height). headless=False mirrors engine.py:
    SDL KMSDRM window + GLES 3.0 (needs the vop service stopped)."""
    if headless:
        ctx = moderngl.create_standalone_context(backend='egl', require=300)
        return ctx, size[0], size[1]

    os.environ["SDL_VIDEODRIVER"] = "kmsdrm"
    import pygame
    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK,
                                    pygame.GL_CONTEXT_PROFILE_ES)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
    w, h = pygame.display.get_desktop_sizes()[0]
    pygame.display.set_mode((w, h),
                            pygame.OPENGL | pygame.DOUBLEBUF | pygame.FULLSCREEN)
    ctx = moderngl.create_context(require=300)
    return ctx, w, h


def make_texture(ctx, kind, w, h):
    """Build a test texture. Each kind has a luma ramp (so Sweep has
    something to bite on) plus detail (so any misplacement shows)."""
    yy, xx = np.mgrid[0:h, 0:w].astype('f4')
    u = xx / (w - 1)
    v = yy / (h - 1)
    if kind == 'pm':
        # Colour ramp + diagonal bands + a 64px checker.
        img = np.stack([u, v, 0.5 + 0.5 * np.sin(18.0 * np.pi * (u + v))], -1)
        checker = ((xx // 64).astype('i4') + (yy // 64).astype('i4')) % 2
        img = img * (0.75 + 0.25 * checker[..., None])
    elif kind == 'bp1':
        # Soft radial vignette: bright centre, dark edges.
        d = np.hypot(u - 0.5, (v - 0.5) * h / w)
        lum = np.clip(1.3 - 2.0 * d, 0.0, 1.0)
        img = lum[..., None] * np.array([1.0, 0.9, 0.8], 'f4')
    else:
        # Diagonal ramp with a hard-edged bright window.
        lum = 0.25 + 0.75 * (0.5 * (u + v))
        window = (u > 0.2) & (u < 0.8) & (v > 0.25) & (v < 0.75)
        lum = np.where(window, 1.0, lum)
        img = np.stack([lum, lum * 0.95, lum], -1)
    data = (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype('u1')
    return ctx.texture((w, h), 3, data.tobytes())

def layer(tex, asp, scale, mpos=(0, 0, -1.0), mrot=(0, 0, 0),
          lpos=(0, 0, 0), lrot=(0, 0, 0), sweep=(0, 0.0), visible=True):
    """One layer's state, in the same terms the engine's state dict uses:
    master pos/rot, local pos/rot, world scale, sweep (mode, width)."""
    f4 = lambda t: np.array(t, dtype='f4')
    return dict(tex=tex, asp=asp, scale=scale, mpos=f4(mpos), mrot=f4(mrot),
                lpos=f4(lpos), lrot=f4(lrot), sweep=sweep, visible=visible)


def clone_scene(sc):
    """Copy a scene so edits don't leak into the original. copy.deepcopy
    can't be used: GPU texture objects can't be copied. The numpy arrays
    inside are only ever replaced, never edited in place, so copying the
    dicts is enough."""
    out = dict(sc)
    for k in ('pm', 'bp1', 'bp2'):
        out[k] = dict(sc[k])
    return out


def build_scenes(tex, asp):
    """The test scenes. 'fit' is the world_scale at which a quad at
    distance 1 exactly fills the screen height for FOV 45."""
    fit = math.tan(math.radians(FOV / 2.0))
    pm_t, b1_t, b2_t = tex['pm'], tex['bp1'], tex['bp2']

    def base(**kw):
        sc = dict(pm=layer(pm_t, asp, 0.85 * fit),
                  bp1=layer(b1_t, asp, 0.60 * fit, mpos=(0.05, 0.02, -1.0)),
                  bp2=layer(b2_t, asp, 0.50 * fit, mpos=(-0.08, -0.03, -1.0)),
                  gel=(1.0, 1.0, 1.0), bg=(0.0, 0.0, 0.0), t=0.5,
                  mono=False, par=(1.0, 1.0))
        sc.update(kw)
        return sc

    def rotated():
        s = base()
        s['pm'].update(mpos=np.array((0.02, 0, -1.1), 'f4'),
                       mrot=np.array((0.03, -0.04, 0.02), 'f4'))
        s['bp1'].update(mrot=np.array((0, 0.08, 0.05), 'f4'),
                        lpos=np.array((0.03, 0.02, 0), 'f4'),
                        lrot=np.array((0.01, 0, 0.02), 'f4'))
        s['bp2'].update(mpos=np.array((0, 0, -0.9), 'f4'),
                        mrot=np.array((0.1, 0, -0.05), 'f4'))
        return s

    scenes = []
    scenes.append(('flat, 3 layers', base()))
    scenes.append(('3D rotated, 3 layers', rotated()))

    s = rotated()                      # BP2 crosses the near plane and
    s['bp2'].update(mpos=np.array((0, 0, -0.2), 'f4'),   # reaches behind
                    mrot=np.array((0.15, 0, 0), 'f4'),   # the camera
                    scale=0.5)
    scenes.append(('near plane + behind camera', s))

    # SWEEP scenes. One layer swept at a time first (so the lit area is big
    # enough to compare), then all three together with mono on.
    s = rotated()
    s['pm']['sweep'] = (1, 0.10)       # PM High Pass
    s['gel'] = (1.0, 0.7, 0.4)
    s['t'] = 0.4
    scenes.append(('sweep PM high-pass + gel', s))

    s = rotated()
    s['bp1']['sweep'] = (2, 0.20)      # BP1 Band Pass
    s['t'] = 0.4
    scenes.append(('sweep BP1 band-pass', s))

    s = rotated()
    s['bp2']['sweep'] = (3, 0.15)      # BP2 Low Pass
    s['t'] = 0.4
    scenes.append(('sweep BP2 low-pass', s))

    s = rotated()
    s['pm']['sweep'] = (1, 0.30)
    s['bp1']['sweep'] = (2, 0.40)
    s['bp2']['sweep'] = (3, 0.40)
    s['mono'] = True
    s['t'] = 0.5
    scenes.append(('sweep all three + mono', s))

    s = rotated()
    s['pm']['visible'] = False         # hidden PM with a sweep = "bulb flash"
    s['pm']['sweep'] = (1, 0.10)
    s['bp2']['visible'] = False
    s['gel'] = (0.8, 0.9, 1.0)
    s['t'] = 0.6
    scenes.append(('hidden PM+BP2, PM sweep', s))

    s = rotated()
    s['par'] = (4.0 / 3.0, 1.0)
    scenes.append(('anamorphic PAR 4:3', s))

    s = base(gel=(0.5, 0.6, 0.7))
    for k in ('pm', 'bp1', 'bp2'):
        s[k]['visible'] = False
    scenes.append(('all hidden + gel', s))

    scenes.append(('preview grey background', base(bg=(0.1, 0.1, 0.1))))
    return scenes

class Rig:
    def __init__(self, ctx, w, h):
        self.ctx, self.w, self.h = ctx, w, h

        # ---- OLD path: the engine's real program/VAO ----------------
        # init_render_pipeline() calls moderngl.create_context(), which
        # would try to build a SECOND context. Hand it ours instead.
        real_create = moderngl.create_context
        moderngl.create_context = lambda *a, **k: ctx
        try:
            _, self.prog, self.vao = gfx.init_render_pipeline()
        finally:
            moderngl.create_context = real_create

        # Same FBO set the engine allocates at boot, plus 'out' standing
        # in for ctx.screen (so both paths can be read back and diffed).
        self.bp1_tex = ctx.texture((w, h), 4)
        self.bp1_fbo = ctx.framebuffer(color_attachments=[self.bp1_tex])
        self.bp2_tex = ctx.texture((w, h), 4)
        self.bp2_fbo = ctx.framebuffer(color_attachments=[self.bp2_tex])
        self.out_tex = ctx.texture((w, h), 4)
        self.out_fbo = ctx.framebuffer(color_attachments=[self.out_tex])
        self.white_tex = ctx.texture((1, 1), 3, bytes([255, 255, 255]))

        # ---- NEW path -----------------------------------------------
        self.new_prog = ctx.program(vertex_shader=NEW_VERT,
                                    fragment_shader=NEW_FRAG)
        quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype='f4')
        self.new_vao = ctx.vertex_array(self.new_prog,
                                        [(ctx.buffer(quad), '2f', 'in_vert')])
        p = self.new_prog
        p['u_screen'].value = (float(w), float(h))
        p['tex_pm'].value = 0           # texture units, fixed for good
        p['tex_bp1'].value = 1
        p['tex_bp2'].value = 2

    # ---- matrix helpers --------------------------------------------
    def mvp(self, L, sc):
        """The engine's real MVP for one layer (bytes, f4, row-major)."""
        return vmath.get_frustum_fit_matrix(
            FOV, L['asp'], L['scale'], L['mpos'], L['mrot'],
            L['lpos'], L['lrot'], self.w, self.h,
            par_x=sc['par'][0], par_y=sc['par'][1], rot_order='XYZ')

    def hinv(self, L, sc):
        """Inverse of the MVP's z-dropped 3x3, ready to upload as mat3."""
        # pyrr stores its matrices transposed relative to GL's column
        # vectors; .T gives the matrix GL actually multiplies by.
        G = np.frombuffer(self.mvp(L, sc), dtype='f4').reshape(4, 4).T
        G = G.astype('f8')
        M3 = G[np.ix_([0, 1, 3], [0, 1, 3])]      # keep x, y, w rows/cols
        try:
            inv = np.linalg.inv(M3)
        except np.linalg.LinAlgError:              # edge-on quad: invisible
            inv = np.zeros((3, 3))
        # GL wants column-major, hence the transpose.
        return np.ascontiguousarray(inv.T, dtype='f4').tobytes()

    # ---- OLD: same passes as engine.render_world -------------------
    def render_old(self, sc):
        ctx, prog, vao = self.ctx, self.prog, self.vao
        prog['mono_mode'].value = bool(sc['mono'])
        prog['sweep_pos'].value = float(sc['t'])

        def set_sweep(cfg):
            prog['sweep_mode'].value = cfg[0]
            prog['sweep_width'].value = cfg[1]

        # PASS 1 + 2: bipack layers into their FBOs
        for key, fbo in (('bp1', self.bp1_fbo), ('bp2', self.bp2_fbo)):
            L = sc[key]
            fbo.use()
            if not L['visible']:
                fbo.clear(1.0, 1.0, 1.0, 1.0)
                continue
            fbo.clear(0.0, 0.0, 0.0, 1.0)
            prog['mvp'].write(self.mvp(L, sc))
            prog['filter_color'].write(np.array([1, 1, 1], dtype='f4'))
            set_sweep(L['sweep'])
            L['tex'].use(0)
            vao.render(moderngl.TRIANGLE_STRIP)

        # PASS 3: PM to the "screen"
        self.out_fbo.use()
        self.out_fbo.clear(*sc['bg'], 1.0)
        pm = sc['pm']
        if pm['visible']:
            mvp, tex = self.mvp(pm, sc), pm['tex']
        else:
            mvp, tex = np.eye(4, dtype='f4').tobytes(), self.white_tex
        prog['mvp'].write(mvp)
        prog['filter_color'].write(np.array(sc['gel'], dtype='f4'))
        set_sweep(pm['sweep'])
        tex.use(0)
        vao.render(moderngl.TRIANGLE_STRIP)

        # PASS 4 + 5: multiply the bipack FBOs over it
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = (moderngl.DST_COLOR, moderngl.ZERO)
        prog['mvp'].write(np.eye(4, dtype='f4').tobytes())
        prog['filter_color'].write(np.array([1, 1, 1], dtype='f4'))
        set_sweep((0, 0.0))
        self.bp1_tex.use(0)
        vao.render(moderngl.TRIANGLE_STRIP)
        self.bp2_tex.use(0)
        vao.render(moderngl.TRIANGLE_STRIP)
        ctx.disable(moderngl.BLEND)

    # ---- NEW: one draw ---------------------------------------------
    def render_new(self, sc):
        p = self.new_prog
        self.out_fbo.use()
        for unit, key in enumerate(('pm', 'bp1', 'bp2')):
            L = sc[key]
            p['on_' + key].value = 1 if L['visible'] else 0
            p['sweep_' + key].value = (float(L['sweep'][0]), float(L['sweep'][1]))
            if L['visible']:
                p['h_' + key].write(self.hinv(L, sc))
                L['tex'].use(unit)
            else:
                self.white_tex.use(unit)    # keep the sampler valid
        p['gel'].value = tuple(float(x) for x in sc['gel'])
        p['bg'].value = tuple(float(x) for x in sc['bg'])
        p['sweep_pos'].value = float(sc['t'])
        p['mono_mode'].value = bool(sc['mono'])
        self.new_vao.render(moderngl.TRIANGLE_STRIP)

    def read_out(self):
        # Read RGBA (the one format every GLES driver must support) and
        # drop the alpha channel ourselves.
        raw = self.out_fbo.read(components=4)
        rgba = np.frombuffer(raw, dtype='u1').reshape(self.h, self.w, 4)
        return rgba[:, :, :3].copy()

def run_diff(rig, scenes, save_dir):
    print("\nPIXEL DIFF  (old three-pass  vs  new single-pass)")
    print(f"{'scene':<30} {'max':>4} {'mean':>7} {'>2 px':>9} {'>8 px':>9} "
          f"{'>32 px':>9}  verdict")
    worst = 0
    for name, sc in scenes:
        rig.render_old(sc)
        a = rig.read_out()
        rig.render_new(sc)
        b = rig.read_out()
        d = np.abs(a.astype('i2') - b.astype('i2')).max(axis=2)
        n2, n8, n32 = int((d > 2).sum()), int((d > 8).sum()), int((d > 32).sum())
        frac8 = n8 / d.size
        ok = frac8 < 0.001               # < 0.1 % of pixels differ visibly
        worst = max(worst, int(d.max()))
        print(f"{name:<30} {int(d.max()):>4} {d.mean():>7.3f} {n2:>9} {n8:>9} "
              f"{n32:>9}  {'OK' if ok else 'LOOK AT PNG'}")
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            slug = name.replace(' ', '_').replace(',', '').replace('+', 'p')
            slug = slug.replace('/', '-').replace(':', '')
            for tag, img in (('old', a), ('new', b),
                             ('diff', np.clip(d * 16, 0, 255).astype('u1')[..., None].repeat(3, 2))):
                # read() is bottom-up, PNG is top-down; RGB -> BGR for cv2.
                cv2.imwrite(os.path.join(save_dir, f"{slug}_{tag}.png"),
                            img[::-1, :, ::-1])
    print(f"worst single-pixel difference over all scenes: {worst} / 255")


def run_timing(rig, scene, frames):
    print(f"\nTIMING  ({frames} frames per row, ms per frame: avg / max)")
    print(f"{'layers on':<18} | {'OLD build':>11} {'OLD GPU':>11} {'OLD total':>10}"
          f" | {'NEW build':>11} {'NEW GPU':>11} {'NEW total':>10} | speedup")
    rows = [('none (all hidden)', ()), ('PM', ('pm',)),
            ('PM + BP1', ('pm', 'bp1')), ('PM + BP1 + BP2', ('pm', 'bp1', 'bp2'))]
    for label, on in rows:
        sc = clone_scene(scene)
        for k in ('pm', 'bp1', 'bp2'):
            sc[k]['visible'] = k in on
        res = []
        for fn in (rig.render_old, rig.render_new):
            for _ in range(5):                 # warm-up: shaders, caches
                fn(sc)
                rig.ctx.finish()
            build, gpu = [], []
            for i in range(frames):
                sc['t'] = i / max(1, frames - 1)
                t0 = time.perf_counter()
                fn(sc)                         # CPU: matrices + GL calls
                t1 = time.perf_counter()
                rig.ctx.finish()               # wait for the GPU
                t2 = time.perf_counter()
                build.append((t1 - t0) * 1000.0)
                gpu.append((t2 - t1) * 1000.0)
            res.append((np.mean(build), np.max(build), np.mean(gpu), np.max(gpu)))
        (ob, obm, og, ogm), (nb, nbm, ng, ngm) = res
        print(f"{label:<18} | {ob:5.1f}/{obm:<5.1f} {og:5.1f}/{ogm:<5.1f} {ob+og:>10.1f}"
              f" | {nb:5.1f}/{nbm:<5.1f} {ng:5.1f}/{ngm:<5.1f} {nb+ng:>10.1f}"
              f" | {(ob+og)/(nb+ng):5.2f}x")

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--headless', action='store_true',
                    help='standalone EGL context instead of the KMSDRM display')
    ap.add_argument('--size', default='2160x1440',
                    help='framebuffer size for --headless (default 2160x1440)')
    ap.add_argument('--tex-size', default='2400x1600',
                    help='synthetic artwork size (default 2400x1600)')
    ap.add_argument('--frames', type=int, default=60)
    ap.add_argument('--save', metavar='DIR')
    ap.add_argument('--no-diff', action='store_true')
    ap.add_argument('--no-timing', action='store_true')
    args = ap.parse_args()

    size = tuple(int(x) for x in args.size.lower().split('x'))
    tw, th = (int(x) for x in args.tex_size.lower().split('x'))

    ctx, w, h = make_context(args.headless, size)
    print(f"GL: {ctx.info['GL_RENDERER']} | {ctx.info['GL_VERSION']}")
    print(f"Framebuffer {w}x{h}, artwork {tw}x{th}")

    rig = Rig(ctx, w, h)
    tex = {k: make_texture(ctx, k, tw, th) for k in ('pm', 'bp1', 'bp2')}
    scenes = build_scenes(tex, tw / th)

    if not args.no_diff:
        run_diff(rig, scenes, args.save)
    if not args.no_timing:
        run_timing(rig, scenes[1][1], args.frames)   # '3D rotated' scene


if __name__ == '__main__':
    main()