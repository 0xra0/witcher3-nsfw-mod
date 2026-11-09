"""Headless: bend Geralt's penis chain so it runs base -> her entrance, then along her canal.

  blender -b in.blend --python bend_penis.py -- bend.json out.blend

bend.json:
  {"body_mesh": "twals_03_wa__body", "entry_rest": [0, 0.036, 0.921], "entry_radius": 0.014,
   "base": [x,y,z], "tip": [x,y,z],     # SMIN shaft in his rest space
   "canal_rest": [0, -0.3, 1],          # canal direction, her pelvis rest space
   "bend_w": 0.025,                     # half-length of the bend round the entrance (m)
   "max_bend_deg": 35,                  # clamp of the outside -> canal angle
   "smooth": 3,                         # +-frames on entrance / canal
   "entry_pelvis": false,               # true: entrance = entry_rest through her pelvis bone
   "entry_offset": [0, 0, 0]}           # added to entry_rest (pelvis rest space) when entry_pelvis

Replaces aim_penis.py (run after stroke.py, before hands_her.py). aim_penis turned the
whole shaft rigidly about its base toward a point past the entrance, so the shaft's line
missed the opening by 1.5-4.5 cm and it slid in sideways ("shoving"); and its weight ramp
left frames 0-45 on the old erection keys, which wobble. Here every joint is aimed at an
arc-length point of a path that is straight from the base to the entrance and turns
smoothly into the canal over +-bend_w, the way Unicorn's bendable chain follows the canal."""
import json, math, os, sys
import bpy
from mathutils import Matrix, Quaternion, Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nla_keys import frame_range, local_of, smooth_list, write

CFG, OUT = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(CFG))
G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]
P = bpy.data.objects["prostitute:CMovingPhysicalAgentComponent2_ARM"]
body = next(o for o in bpy.data.objects if o.type == "MESH" and cfg["body_mesh"] in o.name)
CHAIN = ["penis_%02d" % k for k in range(1, 5)]
B, T = Vector(cfg["base"]), Vector(cfg["tip"])
L = (T - B).length
r_rest = (T - B).normalized()
pbs, bones = G.pose.bones, G.data.bones
AW = G.matrix_world
# Arc length of each joint (and the tip) along the rest shaft.
S = [(bones[n].head_local - B).dot(r_rest) for n in CHAIN] + [L]
e0 = Vector(cfg["entry_rest"])
ring = [v.index for v in body.data.vertices if (v.co - e0).length < cfg["entry_radius"]]
sc = bpy.context.scene
lo, hi = frame_range(G)
frames = list(range(lo, hi + 1))
print("BEND joints at", [round(s, 3) for s in S], "ring", len(ring))


def pelvis_world(A):
    return A.matrix_world @ A.pose.bones["pelvis"].matrix @ A.data.bones["pelvis"].matrix_local.inverted()


def entrance(g):
    sc.frame_set(g)
    # entry_pelvis: her pelvis carries the opening rigidly, so E0 through it is exact. The
    # centroid of the scene mesh's verts near E0 sat 5 mm toward her back on the coarse
    # retail floor (more once the ring keys opened it): the shaft entered 1 cm off centre.
    # entry_offset (her pelvis rest space): the l_01_mg__body shaft surface runs ~4 mm behind
    # the penis bones, and the tunnel mouth sits ~5 mm in front of E0, so the chain aims past E0.
    if cfg.get("entry_pelvis"):
        return pelvis_world(P) @ (e0 + Vector(cfg.get("entry_offset", (0, 0, 0))))
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    v = ev.matrix_world @ (sum((me.vertices[i].co for i in ring), Vector()) / len(ring))
    ev.to_mesh_clear()
    return v


# Her hips sway sideways in the SLAL clip. At the out-stroke only ~3 cm is inside, so a
# 5 cm sideways offset swung the shaft ~25 deg left/right once per stroke (the "wobble").
# Slide her pelvis sideways so the entrance stays on his base line; one pass is exact,
# since a pelvis translation moves the whole skin rigidly.
if cfg.get("center_lateral", True):
    lat = []
    for g in frames:
        v = entrance(g)
        c = (pelvis_world(P).to_3x3() @ Vector(cfg["canal_rest"])).normalized()
        sd = pelvis_world(P).to_3x3() @ Vector((1, 0, 0))
        sd = (sd - c * sd.dot(c)).normalized()
        lat.append(sd * (v - pelvis_world(G) @ B).dot(sd))
    pb = P.pose.bones["pelvis"]
    to_arm = P.matrix_world.to_3x3().inverted()
    loc = {}
    for g, d in zip(frames, lat):
        sc.frame_set(g)
        loc[g] = local_of(P, pb, Matrix.Translation(to_arm @ -d) @ pb.matrix).to_translation()
    write(P, "pelvis", "location", loc)
    print("BEND centred her sideways, max shift %.3f m" % max(d.length for d in lat))

vul, can = [], []
for g in frames:
    vul.append(entrance(g))
    can.append((pelvis_world(P).to_3x3() @ Vector(cfg["canal_rest"])).normalized())
k = cfg.get("smooth", 3)
vul = smooth_list(vul, k)
can = [c.normalized() for c in smooth_list(can, k)]


def path_point(b, v, c, s, w, maxb):
    """Point at arc length s: straight b->v, turning into c over [D-w, D+w]."""
    D = (v - b).length
    u = (v - b).normalized()
    if u.angle(c) > maxb:
        c = u.slerp(c, maxb / u.angle(c))
    p, step, x = b.copy(), 0.002, 0.0
    while x < s - 1e-9:
        h = min(step, s - x)
        m = x + h / 2
        a = min(1.0, max(0.0, (m - (D - w)) / (2 * w)))
        a = a * a * (3 - 2 * a)
        d = u.lerp(c, a).normalized()
        p += d * h
        x += h
    return p


def rotate_about(pb, R, pivot_world):
    A3 = AW.to_3x3().normalized()
    Ra = (A3.inverted() @ R.normalized() @ A3).to_4x4()
    p = AW.inverted() @ pivot_world
    pb.matrix = Matrix.Translation(p) @ Ra @ Matrix.Translation(-p) @ pb.matrix
    pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()


def shaft_dir(n):
    R = (AW @ pbs[n].matrix).to_3x3().normalized() @ bones[n].matrix_local.to_3x3().normalized().inverted()
    return (R @ r_rest).normalized()


w, maxb = cfg.get("bend_w", 0.025), math.radians(cfg.get("max_bend_deg", 35))
keys = {n: {} for n in CHAIN}
for i, g in enumerate(frames):
    sc.frame_set(g)
    # Start from a straight chain: outer joints at rest relative to their parents.
    for n in CHAIN[1:]:
        pb = pbs[n]
        pb.matrix = pb.parent.matrix @ (bones[pb.parent.name].matrix_local.inverted() @ bones[n].matrix_local)
        pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()
    b = pelvis_world(G) @ B
    for j, n in enumerate(CHAIN):
        h = AW @ pbs[n].head if j else b
        goal = path_point(b, vul[i], can[i], S[j + 1], w, maxb)
        rotate_about(pbs[n], shaft_dir(n).rotation_difference(goal - h).to_matrix(), h)
    for n in CHAIN:
        q = pbs[n].rotation_quaternion.copy()
        prev = keys[n].get(g - 1)
        if prev is not None and q.dot(Quaternion(prev)) < 0:
            q.negate()
        keys[n][g] = tuple(q)
    if g % 30 == 0:
        tip = AW @ pbs[CHAIN[-1]].head + shaft_dir(CHAIN[-1]) * (S[4] - S[3])
        u = (vul[i] - b).normalized()
        e = (vul[i] - b) - shaft_dir(CHAIN[0]) * (vul[i] - b).dot(shaft_dir(CHAIN[0]))
        print("BEND f=%3d outside %.3f bend %4.1f deg  base-line miss %.3f  tip depth %.3f"
              % (g, (vul[i] - b).length, math.degrees(u.angle(can[i])), e.length,
                 (tip - vul[i]).dot(can[i])))
for n in CHAIN:
    write(G, n, "rotation_quaternion", keys[n])
bpy.ops.wm.save_as_mainfile(filepath=OUT)
