"""Low-poly header art: forest, village, castle, mountains and a caravan on a forest path.

    blender -b -P art/header.py -- header.png [scene.blend]

Rendered like a late-90s game: soapy low-res tiled textures, no anti-aliasing,
640x200 frame squeezed into a 256-colour VGA palette with ordered dithering.
Scanlines are added in CSS. Everything is procedural and seeded: same script, same picture.
"""
import bisect
import math
import os
import random
import struct
import sys
import zlib

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector, noise
from mathutils.kdtree import KDTree

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(args[0] if args else 'header.png')
BLEND = os.path.abspath(args[1]) if len(args) > 1 else None

rnd = random.Random(19991126)  # Kirill's day one
npr = np.random.default_rng(19991126)
RES = 640, 200
FOG = '#d9a25e'                # dusk haze == sky at the horizon
SKY = [(0.0, FOG), (0.3, '#c98850'), (0.55, '#5e3c3a'), (0.8, '#1a1719'), (1.0, '#0b0d0a')]  # up to frame top
FOG_START, FOG_DIST = 30.0, 260.0
CAM, LOOK, LENS = Vector((0, -40, 6.5)), Vector((0, 40, -0.2)), 20
CASTLE = Vector((80, 215, 0))
VILLAGE = Vector((-34, 32, 0))


def lin(h):
    c = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (1.0,)


# ---------------------------------------------------------------- 90s textures

def smear(a, r, axes=(0, 1)):
    """Tileable box blur (wraps around)."""
    for ax in axes:
        a = sum(np.roll(a, k, ax) for k in range(-r, r + 1)) / (2 * r + 1)
    return a


def grain(n, r=0, axes=(0, 1)):
    a = smear(npr.random((n, n)), r, axes)
    return (a - a.min()) / (a.max() - a.min()) - 0.5  # -0.5..0.5


def tint(v, warm=None):
    """Grey detail around 0.5 (x2 in the shader = neutral); `warm` pushes red up, blue down."""
    w = 0 if warm is None else warm
    return np.dstack([v + w, v, v - w])


TEXTURES = {  # name: (rows = V axis, cols = U axis, rgb); all tiny on purpose
    'grass': lambda: tint(0.5 + 0.35 * grain(32) + 0.25 * grain(32, 2), 0.18 * (grain(32, 3) > 0.15)),
    'dirt': lambda: tint(0.5 + 0.3 * grain(32) + 0.2 * grain(32, 2) + 0.25 * (npr.random((32, 32)) < 0.05), 0.04),
    'needles': lambda: tint(0.5 + 0.7 * grain(16, 2, (0,)) * (0.7 + 0.3 * np.cos(np.arange(16) / 16 * 4 * np.pi))[:, None]),
    'bark': lambda: tint(0.5 + 0.5 * grain(16, 3, (0,)), 0.05),
    'leaves': lambda: tint(0.5 + 0.3 * np.sign(grain(16, 1)) + 0.15 * grain(16), 0.06 * (grain(16, 1) > 0.2)),
    'rock': lambda: tint(0.5 + 0.3 * grain(32, 2) + 0.2 * grain(32), 0.03),
}


def make_texture(name):
    rgb = np.clip(TEXTURES[name](), 0, 1)
    n = rgb.shape[0]
    img = bpy.data.images.new(name, n, n)
    img.colorspace_settings.name = 'Non-Color'
    img.pixels.foreach_set(np.dstack([rgb, np.ones((n, n))]).astype(np.float32).ravel())
    img.pack()
    return img


# ---------------------------------------------------------------- materials

PALETTE = {  # several colours = random pick per object; (colours, texture, metres per tile[, fog])
    'pine': ('#2b6448 #346f4c #24563e #3f7b52 #4c8556 #2f5f4a', 'needles', 3.0),
    'leaf': ('#5f8f4a #77a052 #8aa64e #4f8547', 'leaves', 2.5),
    'bush': ('#4e7f45 #5f8f4c #3e6e44 #6a9550', 'leaves', 0.9),
    'rock': ('#8d8d86 #7c7f7a #a09c92', 'rock', 0.8),
    'tuft': ('#6f9a4c #86a858 #5b8a45 #9aa85a', 'grass', 0.5),
    'trunk': ('#6b4a35', 'bark', 1.5),
    'terrain': (None, 'grass', 8.0), 'path': (None, 'dirt', 5.0),
    'mountain': (None, 'rock', 30.0, '#3a2c3c'),  # dusky silhouettes against the glow
    'stone': '#aaa497', 'stone_dark': '#7d786e', 'plaster': '#d9ccb0',
    'logs': '#8a5a3a', 'timber': '#5e3a26', 'window': '#3a2f2a', 'door': '#5a3a24',
    'roof_orange': '#d98f2b', 'roof_green': '#3f8a4a', 'roof_red': '#a8432f', 'castle_roof': '#8b1a1a',
    'camel': '#c8a065', 'horse_bay': '#7b4a2c', 'horse_dark': '#3d2c24', 'horse_gray': '#cfc8bb',
    'cow': '#ece6d8', 'cow_spot': '#2d2a28', 'muzzle': '#d9a79a', 'horn': '#e8dcc0', 'mane': '#2e2420',
    'skin': '#e0b48a', 'pants': '#4a3b30', 'red': '#a83232', 'blue': '#34558f', 'green': '#4f7a3a',
    'gold': '#d6a632', 'purple': '#6b3f7d', 'white': '#ece6d6', 'teal': '#2f7c78', 'straw': '#d8b86a',
    'burlap': '#c8b07c', 'wood': '#7a4b2a', 'wood_dark': '#5a3a22', 'udder': '#f29aaa',
}  # colours None = per-face colours from the "Col" attribute (terrain, path, mountains)
CLOTH = ['red', 'blue', 'green', 'purple', 'teal', 'white', 'gold']


def color_ramp(nt, stops, interpolation):
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    r = ramp.color_ramp
    r.interpolation = interpolation
    r.elements.remove(r.elements[1])
    r.elements[0].position = stops[0][0]
    for pos, _ in stops[1:]:
        r.elements.new(pos)
    for e, (_, c) in zip(r.elements, stops):
        e.color = lin(c)
    return ramp


def make_material(name, spec):
    colors, tex, tile, fog = (spec + (FOG,))[:4] if isinstance(spec, tuple) else (spec, None, 1, FOG)
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    new, link = nt.nodes.new, nt.links.new

    def op(kind, a, b=None):
        n = new('ShaderNodeMath')
        n.operation = kind
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            elif v is not None:
                link(v, n.inputs[i])
        return n.outputs[0]

    diff = new('ShaderNodeBsdfDiffuse')
    if colors is None:
        a = new('ShaderNodeAttribute')
        a.attribute_name = 'Col'
        color = a.outputs['Color']
    elif ' ' in colors:
        cols = colors.split()
        ramp = color_ramp(nt, [(i / len(cols), c) for i, c in enumerate(cols)], 'CONSTANT')
        link(new('ShaderNodeObjectInfo').outputs['Random'], ramp.inputs['Fac'])
        color = ramp.outputs['Color']
    else:
        diff.inputs['Color'].default_value = lin(colors)
        color = None

    if tex:  # colour x texture x 2, box-mapped in object space, bilinear = soapy
        uv = new('ShaderNodeVectorMath')
        uv.operation, uv.inputs['Scale'].default_value = 'SCALE', 1 / tile
        link(new('ShaderNodeTexCoord').outputs['Object'], uv.inputs[0])
        img = new('ShaderNodeTexImage')
        img.image, img.projection, img.interpolation = TEX[tex], 'BOX', 'Linear'
        link(uv.outputs['Vector'], img.inputs['Vector'])
        mul = new('ShaderNodeVectorMath')
        mul.operation = 'MULTIPLY'
        if color:
            link(color, mul.inputs[0])
        else:
            mul.inputs[0].default_value = lin(colors)[:3]
        link(img.outputs['Color'], mul.inputs[1])
        x2 = new('ShaderNodeVectorMath')
        x2.operation, x2.inputs['Scale'].default_value = 'SCALE', 2.0
        link(mul.outputs['Vector'], x2.inputs[0])
        color = x2.outputs['Vector']
    if color:
        link(color, diff.inputs['Color'])

    # distance fog: 1 - exp(-(d - start) / dist), mixed towards an unlit haze emission
    f = op('SUBTRACT', new('ShaderNodeCameraData').outputs['View Distance'], FOG_START)
    f = op('EXPONENT', op('MULTIPLY', op('MAXIMUM', f, 0.0), -1.0 / FOG_DIST))
    f = op('SUBTRACT', 1.0, f)
    emit = new('ShaderNodeEmission')
    emit.inputs['Color'].default_value = lin(fog)
    mix = new('ShaderNodeMixShader')
    link(f, mix.inputs[0])
    link(diff.outputs[0], mix.inputs[1])
    link(emit.outputs[0], mix.inputs[2])
    link(mix.outputs[0], new('ShaderNodeOutputMaterial').inputs['Surface'])
    return m


# ---------------------------------------------------------------- mesh building

class Model:
    """Primitives merged into one flat-shaded mesh, one material slot per palette name."""

    def __init__(self):
        self.bm, self.mats = bmesh.new(), []

    def paint(self, verts, m, share=1.0):
        if m not in self.mats:
            self.mats.append(m)
        i = self.mats.index(m)
        for f in {f for v in verts if v.is_valid for f in v.link_faces}:
            if share >= 1 or rnd.random() < share:
                f.material_index = i
        return verts

    def box(self, m, loc, size, rot=(0, 0, 0)):
        mx = Matrix.LocRotScale(Vector(loc), Euler(rot), Vector(size))
        return self.paint(bmesh.ops.create_cube(self.bm, size=1, matrix=mx)['verts'], m)

    def cyl(self, m, loc, r1, r2, h, segs=6, rot=(0, 0, 0)):
        mx = Matrix.LocRotScale(Vector(loc), Euler(rot), None)
        v = bmesh.ops.create_cone(self.bm, cap_ends=True, segments=segs, radius1=r1, radius2=r2,
                                  depth=h, matrix=mx)['verts']
        if r2 == 0:
            bmesh.ops.remove_doubles(self.bm, verts=v, dist=1e-4)
        return self.paint(v, m)

    def ball(self, m, loc, size, rot=(0, 0, 0), sub=2):
        size = Vector(size) if isinstance(size, tuple) else Vector((size,) * 3)
        mx = Matrix.LocRotScale(Vector(loc), Euler(rot), size)
        return self.paint(bmesh.ops.create_icosphere(self.bm, subdivisions=sub, radius=1, matrix=mx)['verts'], m)

    def solid(self, m, verts, faces):
        vs = [self.bm.verts.new(v) for v in verts]
        for f in faces:
            self.bm.faces.new([vs[i] for i in f])
        return self.paint(vs, m)

    def mesh(self, name):
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(MAT[m])
        return me


def vcol_mesh(name, verts, faces, colors):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.materials.append(MAT[name])
    attr = me.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
    attr.data.foreach_set('color', [x for p, c in zip(me.polygons, colors) for _ in range(p.loop_total) for x in c])
    return me


def put(data, loc, rz=0.0, s=1.0):
    ob = bpy.data.objects.new(data.name, data)
    ob.location, ob.rotation_euler, ob.scale = loc, (0, 0, rz), (s, s, s)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def shade(c, k):
    return tuple(min(x * k, 1.0) for x in c[:3]) + (1.0,)


def mixc(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


# ---------------------------------------------------------------- path & terrain

def catmull(ctrl, n=24):
    P = [Vector((x, y, 0)) for x, y in ctrl]
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        for k in range(n):
            t = k / n
            out.append(0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3))
    return out + [P[-1]]


PATH = catmull([(-130, -8), (-70, -18), (-35, -13), (-8, -16), (14, -14), (28, -7), (34, 5),
                (29, 20), (21, 34), (25, 50), (38, 66), (52, 80), (64, 96)])
CUM = [0.0]
for a, b in zip(PATH, PATH[1:]):
    CUM.append(CUM[-1] + (b - a).length)


def at(s):
    i = min(max(bisect.bisect(CUM, s) - 1, 0), len(PATH) - 2)
    t = (s - CUM[i]) / (CUM[i + 1] - CUM[i])
    return PATH[i].lerp(PATH[i + 1], t), (PATH[i + 1] - PATH[i]).normalized()


KD = KDTree(int(CUM[-1] / 0.5) + 1)
for i in range(int(CUM[-1] / 0.5) + 1):
    KD.insert(at(i * 0.5)[0], i)
KD.balance()


def path_dist(x, y):
    return KD.find((x, y, 0))[2]


def ground(x, y, d=None):
    d = path_dist(x, y) if d is None else d
    n = noise.noise(Vector((x / 45, y / 45, 0.3))) + 0.5 * noise.noise(Vector((x / 14, y / 14, 1.7)))
    h = n * min(0.6 + max(y, 0) * 0.03, 5.0) + max(y - 60, 0) * 0.03
    r2 = (x - CASTLE.x) ** 2 + (y - CASTLE.y) ** 2
    h += 8 * min(1.0, 1.4 * math.exp(-r2 / (2 * 30 ** 2)))  # flat-topped castle hill
    t = min(max((d - 4.0) / 10.0, 0.0), 1.0)  # the path runs through a flat strip
    return h * t * t * (3 - 2 * t)


def terrain():
    step, x0, y0, nx, ny = 3.0, -540, -60, 361, 178
    verts, dist = [], []
    for j in range(ny):
        for i in range(nx):
            x = x0 + i * step + rnd.uniform(-0.3, 0.3) * step
            y = y0 + j * step + rnd.uniform(-0.3, 0.3) * step
            d = path_dist(x, y)
            verts.append((x, y, ground(x, y, d)))
            dist.append(d)
    faces = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            b, c, d = a + 1, a + nx + 1, a + nx
            faces += [(a, b, c), (a, c, d)] if (i + j) % 2 else [(a, b, d), (b, c, d)]
    grass = [lin(c) for c in ('#6f8a50', '#7d9455', '#8e9f5c', '#9aa865')]
    dry = lin('#b3a873')
    colors = []
    for f in faces:
        cx = sum(verts[k][0] for k in f) / 3
        cy = sum(verts[k][1] for k in f) / 3
        t = min(max(0.5 + 0.7 * noise.noise(Vector((cx / 30, cy / 30, 4.2))), 0.0), 0.999) * (len(grass) - 1)
        c = mixc(grass[int(t)], grass[int(t) + 1], t % 1)
        d = min(dist[k] for k in f)
        if d < 4.0:
            c = mixc(c, dry, (1 - d / 4.0) * 0.7)
        colors.append(shade(c, rnd.uniform(0.94, 1.06)))
    put(vcol_mesh('terrain', verts, faces, colors), (0, 0, 0))


def path_ribbon():
    verts, faces, colors = [], [], []
    sand = lin('#cdb98f')
    s, k = 0.0, 0
    while s < CUM[-1]:
        p, t = at(s)
        side = Vector((-t.y, t.x, 0))
        hw = 1.6 + 0.3 * noise.noise(Vector((s * 0.12, 3.3, 0)))
        verts += [tuple(p + side * hw * rnd.uniform(0.9, 1.1) + Vector((0, 0, 0.07))),
                  tuple(p - side * hw * rnd.uniform(0.9, 1.1) + Vector((0, 0, 0.07)))]
        if k:
            a = 2 * (k - 1)
            faces += [(a, a + 2, a + 3), (a, a + 3, a + 1)]
            colors += [shade(sand, rnd.uniform(0.93, 1.05)) for _ in range(2)]
        s, k = s + 1.0, k + 1
    put(vcol_mesh('path', verts, faces, colors), (0, 0, 0))


# ---------------------------------------------------------------- scenery

def pines():
    out = []
    for tiers, segs in ((3, 6), (4, 7), (2, 6), (3, 7)):
        m = Model()
        m.cyl('trunk', (0, 0, 0.6), 0.2, 0.14, 1.2, segs=5)
        z, r, h = 0.8, 1.7, 2.4
        for _ in range(tiers):
            m.cyl('pine', (0, 0, z + h / 2), r, 0, h, segs=segs, rot=(0, 0, rnd.uniform(0, 6)))
            z, r, h = z + h * 0.5, r * 0.76, h * 0.86
        out.append(m.mesh('pine'))
    m = Model()  # tall single cone
    m.cyl('trunk', (0, 0, 0.6), 0.2, 0.14, 1.2, segs=5)
    m.cyl('pine', (0, 0, 0.8 + 3.2), 1.45, 0, 6.4, segs=7)
    out.append(m.mesh('pine'))
    return out


def leafy():
    m = Model()
    m.cyl('trunk', (0, 0, 1.1), 0.22, 0.16, 2.2, segs=5)
    m.ball('leaf', (0, 0, 3.2), (1.7, 1.7, 1.9), sub=1)
    return m.mesh('leafy')


def blob(name, size, jitter, sub=1):
    m = Model()
    v = m.ball(name, (0, 0, 0), size, sub=sub)
    for x in v:
        x.co *= rnd.uniform(1 - jitter, 1 + jitter)
    return m.mesh(name)


def tuft():
    m = Model()
    for _ in range(5):
        a = rnd.uniform(0, 6.28)
        m.cyl('tuft', (math.cos(a) * 0.12, math.sin(a) * 0.12, 0.22), 0.06, 0, rnd.uniform(0.35, 0.6), segs=3,
              rot=(rnd.uniform(-0.4, 0.4), rnd.uniform(-0.4, 0.4), 0))
    return m.mesh('tuft')


def house(w, d, h, roof, wall):
    m = Model()
    m.box('stone', (0, 0, 0), (w + 0.3, d + 0.3, 1.2))
    m.box(wall, (0, 0, 0.6 + h / 2), (w, d, h))
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.box('timber', (sx * w / 2, sy * d / 2, 0.6 + h / 2), (0.26, 0.26, h))
    z0, rh = 0.6 + h, d * 0.55
    m.box('timber', (0, 0, z0), (w + 0.12, d + 0.12, 0.22))
    m.solid(wall, [(-w / 2, -d / 2, z0), (-w / 2, d / 2, z0), (-w / 2, 0, z0 + rh),
                   (w / 2, -d / 2, z0), (w / 2, d / 2, z0), (w / 2, 0, z0 + rh)],
            [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)])
    ang, L = math.atan2(rh, d / 2), math.hypot(d / 2, rh) + 0.45
    for s in (-1, 1):
        n = Vector((0, s * math.sin(ang), math.cos(ang)))
        c = Vector((0, s * math.cos(ang) * L / 2, z0 + rh - math.sin(ang) * L / 2)) + n * 0.1
        m.box(roof, c, (w + 0.8, L, 0.2), rot=(-s * ang, 0, 0))
    m.box('stone_dark', (w * 0.28, d * 0.2, z0 + (rh + 0.9) / 2), (0.65, 0.65, rh + 0.9))
    m.box('door', (0, -d / 2 - 0.04, 0.6 + 0.85), (0.9, 0.12, 1.7))
    for sy in (-1, 1):
        for sx in (-0.32, 0.32):
            if sy < 0 or rnd.random() < 0.7:
                m.box('window', (sx * w, sy * (d / 2 + 0.04), 0.6 + h * 0.58), (0.7, 0.12, 0.7))
    for sx in (-1, 1):
        m.box('window', (sx * (w / 2 + 0.04), 0, 0.6 + h * 0.58), (0.12, 0.7, 0.7))
    return m.mesh('house')


def castle():
    m = Model()
    S, H, T = 30.0, 10.0, 2.4
    m.box('stone_dark', (0, 0, -3), (S + 6, S + 6, 8))
    for i in range(4):
        a = i * math.pi / 2
        cx, cy = math.cos(a) * S / 2, math.sin(a) * S / 2
        along = Vector((-math.sin(a), math.cos(a), 0))
        m.box('stone', (cx, cy, H / 2), (T if i % 2 == 0 else S, S if i % 2 == 0 else T, H))
        for k in range(-6, 7):
            p = Vector((cx, cy, H + 0.6)) + along * k * 2.2
            m.box('stone', p, (1.1, 1.1, 1.2))
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.cyl('stone', (sx * S / 2, sy * S / 2, 8), 3.2, 3.0, 16, segs=8)
            m.cyl('castle_roof', (sx * S / 2, sy * S / 2, 16 + 3.6), 3.9, 0, 7.2, segs=8)
    m.box('stone', (3, 4, 12), (12, 12, 24))
    m.cyl('castle_roof', (3, 4, 24 + 4), 9.2, 0, 8, segs=4, rot=(0, 0, math.pi / 4))
    m.cyl('stone', (-6, -4, 17), 2.8, 2.6, 34, segs=8)
    m.cyl('castle_roof', (-6, -4, 34 + 4.5), 3.6, 0, 9, segs=8)
    m.box('wood_dark', (-6, -4, 45), (0.2, 0.2, 4))
    m.box('castle_roof', (-4.9, -4, 46), (2.2, 0.1, 1.3))
    m.box('door', (0, -S / 2 - T / 2, 3), (4.5, 0.4, 6))
    for x in (-8, 8):
        m.box('window', (x, -S / 2 - T / 2, 6.5), (1, 0.3, 1.8))
    return m.mesh('castle')


def mountain(r, h):
    segs, rings = 11, 5
    verts = []
    for k in range(rings):
        t = k / rings
        for i in range(segs):
            a = math.tau * i / segs + rnd.uniform(-0.18, 0.18) + k * 0.4
            rad = r * (1 - t) ** 1.15 * rnd.uniform(0.8, 1.15)
            verts.append((math.cos(a) * rad, math.sin(a) * rad, h * t + (rnd.uniform(-0.07, 0.07) * h if k else -h * 0.15)))
    verts.append((rnd.uniform(-0.08, 0.08) * r, rnd.uniform(-0.08, 0.08) * r, h * rnd.uniform(0.95, 1.05)))
    faces = []
    for k in range(rings - 1):
        for i in range(segs):
            a, b = k * segs + i, k * segs + (i + 1) % segs
            faces += [(a, b, b + segs), (a, b + segs, a + segs)]
    top = len(verts) - 1
    faces += [((rings - 1) * segs + i, (rings - 1) * segs + (i + 1) % segs, top) for i in range(segs)]
    rock = [lin(c) for c in ('#6f7c74', '#7f8a80', '#8d958b', '#66756b')]
    snow, forest = lin('#eef0ee'), lin('#4f6f56')
    colors = []
    for f in faces:
        z = sum(verts[k][2] for k in f) / 3
        c = snow if z > h * rnd.uniform(0.6, 0.75) else forest if z < h * rnd.uniform(0.1, 0.25) else rnd.choice(rock)
        colors.append(shade(c, rnd.uniform(0.95, 1.05)))
    return vcol_mesh('mountain', verts, faces, colors)


# ---------------------------------------------------------------- caravan

def person(m, x=0.0, z=0.0, seated=False, staff=False, load=False):
    c = rnd.choice(CLOTH)
    if seated:
        for sy in (-0.3, 0.3):
            m.box('pants', (x + 0.12, sy, z - 0.22), (0.16, 0.14, 0.62), rot=(0, -0.3, 0))
    else:
        for sy in (-0.1, 0.1):
            m.box('pants', (x, sy, z + 0.4), (0.15, 0.14, 0.8))
        z += 0.8
    m.cyl(c, (x, 0, z + 0.35), 0.3, 0.2, 0.7, segs=6)
    for sy in (-0.27, 0.27):
        m.box(c, (x, sy, z + 0.4), (0.12, 0.12, 0.56))
    m.ball('skin', (x, 0, z + 0.88), 0.17, sub=1)
    hat = rnd.choice(('cone', 'turban', 'cone', 'none'))
    if hat == 'cone':
        m.cyl(rnd.choice(('straw', 'red', 'burlap')), (x, 0, z + 1.12), 0.24, 0, 0.36, segs=6)
    elif hat == 'turban':
        m.ball('white', (x, 0, z + 1.02), (0.2, 0.2, 0.13), sub=1)
    if staff:
        m.box('wood', (x + 0.12, 0.33, z + 0.25), (0.06, 0.06, 2.1))
    if load:
        m.ball('burlap', (x - 0.28, 0, z + 0.55), (0.2, 0.26, 0.3), sub=1)


def sack(m, loc, s=0.3):
    m.ball('burlap', loc, (s, s * 0.85, s * 1.1), sub=1)


def chest(m, loc, size):
    m.box('wood', loc, size)
    m.box('gold', loc, (size[0] * 0.18, size[1] + 0.03, size[2] + 0.03))


def roll(m, loc, length=1.3):
    m.cyl(rnd.choice(CLOTH), loc, 0.15, 0.15, length, segs=6, rot=(math.pi / 2, 0, 0))


def barrel(m, loc):
    m.cyl('wood', loc, 0.24, 0.24, 0.62, segs=8, rot=(math.pi / 2, 0, 0))
    for dy in (-0.2, 0.2):
        m.cyl('wood_dark', (loc[0], loc[1] + dy, loc[2]), 0.25, 0.25, 0.06, segs=8, rot=(math.pi / 2, 0, 0))


def legs(m, coat, xs, ys, h, w=0.15):
    for sx in xs:
        for sy in ys:
            m.box(coat, (sx, sy, h / 2), (w, w, h))


def camel():
    m = Model()
    legs(m, 'camel', (-0.6, 0.6), (-0.2, 0.2), 1.3, 0.16)
    m.ball('camel', (0, 0, 1.5), (1.0, 0.42, 0.42))
    m.ball('camel', (-0.05, 0, 1.92), (0.45, 0.32, 0.36))
    m.box('camel', (1.05, 0, 1.75), (0.24, 0.22, 0.8), rot=(0, 0.75, 0))
    m.box('camel', (1.45, 0, 2.08), (0.52, 0.2, 0.22), rot=(0, 0.15, 0))
    m.box('camel', (-1.0, 0, 1.3), (0.06, 0.06, 0.5), rot=(0, 0.3, 0))
    bag = rnd.choice(CLOTH)
    for sy in (-1, 1):
        m.box(bag, (-0.1, sy * 0.48, 1.45), (0.7, 0.2, 0.55))
        m.box('gold', (-0.1, sy * 0.585, 1.45), (0.72, 0.02, 0.08))
    roll(m, (-0.6, 0, 1.98))
    sack(m, (0.5, 0, 2.06), 0.24)
    return m.mesh('camel')


def horse(rider):
    m = Model()
    coat = rnd.choice(('horse_bay', 'horse_dark', 'horse_gray'))
    legs(m, coat, (-0.55, 0.55), (-0.17, 0.17), 1.0, 0.14)
    m.ball(coat, (0, 0, 1.2), (0.85, 0.34, 0.36))
    m.box(coat, (0.8, 0, 1.55), (0.26, 0.22, 0.75), rot=(0, 0.6, 0))
    m.box(coat, (1.12, 0, 1.78), (0.52, 0.18, 0.22), rot=(0, 0.5, 0))
    m.box('mane', (0.69, 0, 1.62), (0.1, 0.08, 0.7), rot=(0, 0.6, 0))
    m.box('mane', (-0.92, 0, 1.0), (0.1, 0.1, 0.65), rot=(0, 0.35, 0))
    m.box(rnd.choice(CLOTH), (-0.05, 0, 1.57), (0.7, 0.8, 0.05))
    if rider:
        person(m, -0.05, 1.6, seated=True)
    else:
        for sy in (-1, 1):
            chest(m, (-0.05, sy * 0.46, 1.25), (0.6, 0.22, 0.42))
        barrel(m, (-0.05, 0, 1.84))
    return m.mesh('horse')


def cow():
    m = Model()
    legs(m, 'cow', (-0.55, 0.55), (-0.22, 0.22), 0.76, 0.16)
    m.paint(m.ball('cow', (0, 0, 1.0), (0.9, 0.42, 0.36)), 'cow_spot', share=0.35)
    m.box('cow', (1.0, 0, 1.12), (0.42, 0.32, 0.36), rot=(0, 0.3, 0))
    m.box('muzzle', (1.2, 0, 1.02), (0.14, 0.3, 0.2))
    for sy in (-1, 1):
        m.cyl('horn', (0.95, sy * 0.22, 1.36), 0.05, 0, 0.26, segs=4, rot=(sy * 0.7, 0, 0))
    m.box('cow', (-0.92, 0, 0.85), (0.06, 0.06, 0.6), rot=(0, 0.2, 0))
    m.ball('udder', (-0.38, 0, 0.6), (0.32, 0.26, 0.2), sub=1)
    for sx in (-0.09, 0.09):
        for sy in (-0.08, 0.08):
            m.cyl('udder', (-0.38 + sx, sy, 0.38), 0.045, 0.03, 0.16, segs=4)
    for sy in (-1, 1):
        sack(m, (-0.25, sy * 0.3, 1.38), 0.26)
    chest(m, (0.3, 0, 1.5), (0.42, 0.46, 0.32))
    return m.mesh('cow')


def walker(staff=False):
    m = Model()
    person(m, staff=staff, load=not staff and rnd.random() < 0.6)
    return m.mesh('walker')


TRAIN = [  # front to back: (builder, length along the path, sideways offset)
    (lambda: walker(staff=True), 1.6, 0.2), (camel, 3.6, 0), (camel, 3.6, 0), (walker, 1.6, -0.5),
    (lambda: horse(True), 3.0, 0), (cow, 2.8, 0), (walker, 1.4, 0.6), (camel, 3.6, 0),
    (lambda: horse(False), 3.0, 0), (cow, 2.8, 0), (walker, 1.6, -0.3), (lambda: horse(False), 3.0, 0),
    (camel, 3.6, 0), (walker, 1.6, 0.4),
]


def caravan(front_x):
    s = next(CUM[i] for i, p in enumerate(PATH) if p.x > front_x)
    for build, length, off in TRAIN:
        p, t = at(s - length / 2)
        side = Vector((-t.y, t.x, 0))
        put(build(), p + side * (off + rnd.uniform(-0.15, 0.15)) + Vector((0, 0, 0.07)),
            math.atan2(t.y, t.x) + rnd.uniform(-0.08, 0.08))
        s -= length + 0.5


# ---------------------------------------------------------------- scene

def in_view(x, y, margin=6.0):
    dy = y - CAM.y
    return dy > 3 and abs(x) < dy * (18 / LENS) + margin


def populate():
    terrain()
    path_ribbon()
    caravan(front_x=16)

    clear = [(VILLAGE.x, VILLAGE.y, 17), (-26, 12, 12), (CASTLE.x, CASTLE.y, 30)]
    houses = [(0, 0), (-9, 4), (8, 5), (-3, 12), (10, -5), (-11, -6), (4, 18)]
    houses = [(VILLAGE.x + dx, VILLAGE.y + dy) for dx, dy in houses] + [(-17, 12)]
    for x, y in houses:
        roof = rnd.choice(('roof_orange', 'roof_orange', 'roof_green', 'roof_red'))
        me = house(rnd.uniform(5, 6.8), rnd.uniform(3.8, 4.6), rnd.uniform(2.4, 2.9), roof,
                   rnd.choice(('plaster', 'logs')))
        put(me, (x, y, ground(x, y)), rnd.uniform(-0.6, 0.6) + (math.pi if rnd.random() < 0.2 else 0))
        clear.append((x, y, 6.5))

    put(castle(), (CASTLE.x, CASTLE.y, ground(CASTLE.x, CASTLE.y) - 0.5), -0.25, 0.8)
    for i in range(16):  # two ridges behind the castle
        far = i % 2
        x = -520 + i * 66 + rnd.uniform(-20, 20)
        y = 330 + far * 80 + rnd.uniform(-25, 25)
        h = rnd.uniform(28, 48) * (1.35 if far else 1.0)
        put(mountain(rnd.uniform(70, 110) * (1.3 if far else 1.0), h), (x, y, ground(x, y) - 6), rnd.uniform(0, 6))

    trees, broad = pines(), leafy()
    for gx in range(-260, 260, 3):
        for gy in range(-30, 260, 3):
            x, y = gx + rnd.uniform(-1.4, 1.4), gy + rnd.uniform(-1.4, 1.4)
            if not in_view(x, y) or noise.noise(Vector((x / 38, y / 38, 5.0))) < -0.3 or rnd.random() < 0.25:
                continue
            s = rnd.uniform(1.1, 1.9) if y > 2 else rnd.uniform(0.8, 1.25)
            d = path_dist(x, y)
            if d < 3.0 + 1.2 * s or any(math.hypot(x - cx, y - cy) < r for cx, cy, r in clear):
                continue
            if y < -24 or y < 2 and abs(x) < (y - CAM.y) * 0.62:  # keep the caravan in plain view
                continue
            put(broad if rnd.random() < 0.08 else rnd.choice(trees), (x, y, ground(x, y, d) - 0.3),
                rnd.uniform(0, 6.28), s)

    bush, tufty = blob('bush', (0.55, 0.55, 0.4), 0.15), tuft()
    rocks = [blob('rock', (0.4, 0.32, 0.26), 0.25) for _ in range(3)]
    for _ in range(2500):
        x, y = rnd.uniform(-60, 60), rnd.uniform(-24, 40)
        d = path_dist(x, y)
        if not in_view(x, y, 2) or d < 2.2:
            continue
        r = rnd.random()
        me = tufty if r < 0.7 else bush if r < 0.88 else rnd.choice(rocks)
        put(me, (x, y, ground(x, y, d) - 0.05), rnd.uniform(0, 6.28), rnd.uniform(0.7, 1.4))


def setup():
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.eevee.taa_render_samples = 1  # no anti-aliasing, jaggies are part of the look
    sc.render.filter_size = 0.0
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.view_settings.view_transform = 'Standard'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = OUT

    world = bpy.data.worlds.new('sky')
    sc.world = world
    nt = world.node_tree
    nt.nodes.clear()
    new, link = nt.nodes.new, nt.links.new
    # camera sees a dusk gradient by elevation: haze at the horizon, night at the frame top
    up = new('ShaderNodeSeparateXYZ')
    link(new('ShaderNodeTexCoord').outputs['Generated'], up.inputs[0])
    flat = (LOOK - CAM).to_2d().length
    top = math.atan2(LOOK.z - CAM.z, flat) + math.atan(18 / LENS * RES[1] / RES[0])
    span = new('ShaderNodeMapRange')
    span.inputs['From Max'].default_value = math.sin(top)
    link(up.outputs['Z'], span.inputs['Value'])
    ramp = color_ramp(nt, SKY, 'LINEAR')
    link(span.outputs['Result'], ramp.inputs['Fac'])
    sky, amb = new('ShaderNodeBackground'), new('ShaderNodeBackground')
    link(ramp.outputs['Color'], sky.inputs['Color'])
    amb.inputs['Color'].default_value, amb.inputs['Strength'].default_value = lin('#7f8fb0'), 0.5
    mix = new('ShaderNodeMixShader')
    link(new('ShaderNodeLightPath').outputs['Is Camera Ray'], mix.inputs[0])
    link(amb.outputs[0], mix.inputs[1])
    link(sky.outputs[0], mix.inputs[2])
    link(mix.outputs[0], new('ShaderNodeOutputWorld').inputs['Surface'])

    sun = bpy.data.lights.new('sun', 'SUN')  # low evening sun from the left
    sun.energy, sun.angle, sun.color = 2.8, math.radians(2), lin('#ffc98a')[:3]
    put(sun, (0, 0, 50)).rotation_euler = Vector((0.65, 0.6, -0.35)).to_track_quat('-Z', 'Y').to_euler()

    cam = bpy.data.cameras.new('cam')
    cam.lens, cam.sensor_width, cam.sensor_fit, cam.clip_end = LENS, 36, 'HORIZONTAL', 3000
    ob = put(cam, CAM)
    ob.rotation_euler = (LOOK - CAM).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = ob


BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16 - 0.5


def vga(path, colors=256, dither=1 / 32):
    """Squeeze the render into a 256-colour palette (median cut, 6-bit DAC) with Bayer dithering."""
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[..., :3]

    boxes = [px.reshape(-1, 3)]
    while len(boxes) < colors:
        i = max(range(len(boxes)), key=lambda k: np.ptp(boxes[k], 0).max())
        b = boxes.pop(i)
        ch = np.ptp(b, 0).argmax()
        b = b[b[:, ch].argsort()]
        boxes += [b[:len(b) // 2], b[len(b) // 2:]]
    pal = np.round(np.array([b.mean(0) for b in boxes]) * 63) / 63

    px = px + dither * np.tile(BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w, None]
    flat = px.reshape(-1, 3)
    idx = np.concatenate([((c[:, None] - pal[None]) ** 2).sum(-1).argmin(1) for c in np.array_split(flat, 32)])
    rows = idx.reshape(h, w)[::-1].astype(np.uint8)  # Blender pixels are bottom-up

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))

    with open(path, 'wb') as f:  # indexed PNG: a real 256-colour image, ~3x smaller than RGB
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 3, 0, 0, 0))
                + chunk(b'PLTE', np.round(pal * 255).astype(np.uint8).tobytes())
                + chunk(b'IDAT', zlib.compress(b''.join(b'\0' + r.tobytes() for r in rows), 9))
                + chunk(b'IEND', b''))


bpy.ops.wm.read_factory_settings(use_empty=True)
TEX = {k: make_texture(k) for k in TEXTURES}
MAT = {k: make_material(k, v) for k, v in PALETTE.items()}
setup()
populate()
if BLEND:
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
bpy.ops.render.render(write_still=True)
vga(OUT)
