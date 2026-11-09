"""Headless: give her the entrance ring (tools/entrance_bones.py) and key it round the shaft.

  blender -b in.blend --python open_entrance.py -- open.json out.blend

open.json:
  {"base": [x,y,z], "tip": [x,y,z],     # SMIN shaft in his rest space (as bend.json)
   "radius": [[s, r], ...],             # shaft radius at arc length s from the base (m)
   "open_scale": 0.9,                   # hole radius / shaft radius (lips hug the shaft)
   "ramp": 0.02,                        # depth over which the hole opens as the tip enters
   "drag_k": 0.03, "drag_max": 0.006,   # lips follow the stroke: shift = k * depth speed
   "drag_in": 0.003,                    # constant inward pull while he is inside
   "smooth": 2,
   "entry_pelvis": false}               # true: the opening is E0 through her pelvis bone

Run after bend_penis.py (the shaft must be final). The scene mesh has no hole, so before
this the shaft just pierced the painted slit; now the skin round the opening is moved
off her pelvis onto six ring bones that spread to the shaft's radius where it crosses the
entrance and slide a few mm along the canal with the in/out speed, the way Unicorn's
entrance stretches and drags. The ring bones are added to her cutscene armature (exported
tracks 94..105, matching the patched woman_base.w2rig) and, for previews, to the armatures
her body mesh follows, with matching vertex groups."""
import json, os, sys
import bpy
from mathutils import Matrix, Vector
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from nla_keys import _fcurves, frame_range, smooth_list, track, write
import entrance_bones as eb

CFG, OUT = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(CFG))
G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]
P = bpy.data.objects["prostitute:CMovingPhysicalAgentComponent2_ARM"]
body = next(o for o in bpy.data.objects if o.type == "MESH" and "twals_03_wa__body" in o.name)
CHAIN = ["penis_%02d" % k for k in range(1, 5)]
sc = bpy.context.scene
lo, hi = frame_range(P)
frames = list(range(lo, hi + 1))
E0, CAN = Vector(eb.E0), Vector(eb.CANAL)
Bs, Ts = Vector(cfg["base"]), Vector(cfg["tip"])
L = (Ts - Bs).length
r_rest = (Ts - Bs).normalized()
ring_v = [v.index for v in body.data.vertices if (v.co - E0).length < 0.014]


def pelvis_world(A):
    return A.matrix_world @ A.pose.bones["pelvis"].matrix @ A.data.bones["pelvis"].matrix_local.inverted()


def radius(s):
    pts = cfg["radius"]
    if s <= pts[0][0]:
        return pts[0][1]
    for (s0, r0), (s1, r1) in zip(pts, pts[1:]):
        if s <= s1:
            return r0 + (r1 - r0) * (s - s0) / (s1 - s0)
    return pts[-1][1]


# rekey_only: the bones, skinning and channels already exist (a re-run after restroke.py);
# only the keys are rewritten, for the ring bones this armature actually has. The old keys
# are zeroed first so the measurement sees the skin as section 1 always has.
REKEY = cfg.get("rekey_only", False)
if REKEY:
    for n in eb.ALL:
        if n in P.pose.bones:
            write(P, n, "location", {g: (0.0, 0.0, 0.0) for g in frames})

# 1. Measure, before anything of hers changes: where the shaft crosses her entrance.
depth, vul = [], []
for g in frames:
    sc.frame_set(g)
    if cfg.get("entry_pelvis"):
        v = pelvis_world(P) @ E0         # as bend_penis.py entry_pelvis
    else:
        ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        v = ev.matrix_world @ (sum((me.vertices[i].co for i in ring_v), Vector()) / len(ring_v))
        ev.to_mesh_clear()
    c = (pelvis_world(P).to_3x3() @ CAN).normalized()
    n = CHAIN[-1]
    R = (G.matrix_world @ G.pose.bones[n].matrix).to_3x3().normalized() @ \
        G.data.bones[n].matrix_local.to_3x3().normalized().inverted()
    s4 = (G.data.bones[n].head_local - Bs).dot(r_rest)
    tip = G.matrix_world @ G.pose.bones[n].head + (R @ r_rest).normalized() * (L - s4)
    depth.append((tip - v).dot(c))
    vul.append(v)


def ss(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


k_open = cfg.get("open_scale", 0.9)
openr = [k_open * radius(L - d) * ss(d / cfg.get("ramp", 0.02)) for d in depth]
fps = sc.render.fps / sc.render.fps_base
speed = [0.0] + [(depth[i] - depth[i - 1]) * fps for i in range(1, len(depth))]
dm = cfg.get("drag_max", 0.006)
drag = [max(-dm, min(dm, cfg.get("drag_k", 0.03) * sp)) + cfg.get("drag_in", 0.003) * ss(d / 0.02)
        for sp, d in zip(speed, depth)]
h = cfg.get("smooth", 2)
openr, drag = smooth_list(openr, h), smooth_list(drag, h)

# 2. Bones: on her cutscene armature, and down the chain of armatures her mesh copies.
def add_bones(A, names=eb.ALL):
    bpy.context.view_layer.objects.active = A
    for o in bpy.context.selected_objects:
        o.select_set(False)
    A.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    pel = A.data.edit_bones["pelvis"]
    rot = pel.matrix.to_3x3()
    for n in names:
        h = Vector(eb.bone_position(n))
        e = A.data.edit_bones.get(n) or A.data.edit_bones.new(n)
        e.head, e.tail = h, h + rot.col[1] * 0.01
        e.matrix = Matrix.Translation(h) @ rot.to_4x4()
        e.parent = pel
    bpy.ops.object.mode_set(mode="OBJECT")


def add_tracks(names):
    """Bones on her cutscene armature, in its export order, with flat rest channels in every strip."""
    add_bones(P, names)
    order = P.data.witcherui_RigSettings.bone_order_list
    have = [b.name for b in order]
    for n in names:
        if n not in have:
            order.add().name = n
    print("OPEN order", len(order), [b.name for b in order][-7:])
    for strip in track(P).strips:
        fcs = _fcurves(strip.action)
        n_k = int(round(strip.frame_end)) - int(round(strip.frame_start)) + 1
        for n in names:
            P.pose.bones[n].rotation_mode = "QUATERNION"
            path = 'pose.bones["%s"]' % n
            for fc in [fc for fc in fcs if fc.data_path.startswith(path)]:
                fcs.remove(fc)
            for prop, rest in (("location", (0, 0, 0)), ("rotation_quaternion", (1, 0, 0, 0))):
                for i, v in enumerate(rest):
                    fc = fcs.new(path + "." + prop, index=i, group_name=n)
                    fc.keyframe_points.add(n_k)
                    fc.keyframe_points.foreach_set("co", [x for k in range(n_k) for x in (float(k), float(v))])
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"
                    fc.update()


# rekey_only with add_missing: ring bones the game mesh skins to but this armature lacks
# (the lip ring, added after p27) get tracks too. Without them the game leaves those bones
# unanimated and the skin on them is torn toward her pelvis. The scene mesh isn't
# reskinned, so previews show only the inner ring.
if REKEY and cfg.get("add_missing"):
    missing = [n for n in eb.ALL if n not in P.pose.bones]
    if missing:
        add_tracks(missing)

if not REKEY:
    add_tracks(eb.ALL)

    A = body.modifiers[0].object
    followers = []
    while A is not P:
        con = next(c for c in A.pose.bones["pelvis"].constraints if c.type == "COPY_TRANSFORMS")
        followers.append((A, con.target))
        A = con.target
    for A, src in followers:
        add_bones(A)
        for n in eb.ALL:
            c = A.pose.bones[n].constraints.new("COPY_TRANSFORMS")
            c.target, c.subtarget = src, n
    print("OPEN followers", [a.name.split("\\")[-1] for a, _ in followers])

    vg = body.vertex_groups
    pel_i = vg["pelvis"].index
    groups = {n: vg.get(n) or vg.new(name=n) for n in eb.ALL}
    moved = 0
    for v in body.data.vertices:
        old = {g.group: g.weight for g in v.groups if g.weight > 0}
        tot = sum(old.values())
        if not tot:
            continue
        norm = {b: w / tot for b, w in old.items()}
        new = eb.take(norm, pel_i, tuple(v.co))
        if new == norm:
            continue
        for b in old:
            if b not in new:
                vg[b].remove([v.index])
        for b, w in new.items():
            (groups[b] if isinstance(b, str) else vg[b]).add([v.index], w, "REPLACE")
        moved += 1
    print("OPEN reskinned %d scene verts" % moved)

# 3. Keys: the per-frame translation (channels exist from add_tracks or an earlier run).
for k, n in enumerate(eb.NAMES):
    to_local = P.data.bones[n].matrix_local.to_3x3().inverted()
    d = Vector(eb.direction(k))
    write(P, n, "location", {g: tuple(to_local @ (d * o + CAN * dr)) for g, o, dr in zip(frames, openr, drag)})

# Lip ring: friction drags the rim the way the shaft moves (in on the push, out on the
# pull) and the pull puffs it outward. Normalised to the scene's own stroke speed.
spd = smooth_list(speed, h)
ref = sorted(abs(x) for x in spd)[int(0.9 * (len(spd) - 1))] or 1.0
inside = [ss(d / 0.02) for d in depth]
u = [max(-1.0, min(1.0, x / ref)) for x in spd]
lip_drag = [cfg.get("lip_drag", 0.010) * x * w for x, w in zip(u, inside)]
lip_puff = [(cfg.get("lip_puff0", 0.002) + cfg.get("lip_puff", 0.004) * max(0.0, -x)) * w
            for x, w in zip(u, inside)]
lip_drag, lip_puff = smooth_list(lip_drag, h), smooth_list(lip_puff, h)
for k, n in enumerate(eb.LIP_NAMES):
    if n not in P.pose.bones:
        continue
    to_local = P.data.bones[n].matrix_local.to_3x3().inverted()
    d = Vector(eb.direction(k))
    write(P, n, "location", {g: tuple(to_local @ (d * o + CAN * dr)) for g, o, dr in zip(frames, lip_puff, lip_drag)})
print("OPEN lip ref speed %.3f m/s, drag range %+.4f..%+.4f" % (ref, min(lip_drag), max(lip_drag)))

for i in range(0, len(frames), 30):
    print("OPEN f=%3d depth %.3f hole r %.3f drag %+.4f" % (frames[i], depth[i], openr[i], drag[i]))
sc.frame_set(lo)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
