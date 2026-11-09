"""Headless: aim Geralt's penis chain into the prostitute's vulva on every frame.

  blender -b in.blend --python aim_penis.py -- aim.json out.blend

Run after add_penis_bones.py (the chain must exist and be keyed). aim.json:
  {"body_mesh": "twals_03_wa__body", "vulva_verts": [488, 1107],
   "base": [x,y,z], "tip": [x,y,z],         # SMIN shaft in Geralt's rest space
   "depth": 0.05,                           # aim this far past the vulva, into her
   "max_deg": 60,                           # clamp of the aim rotation
   "weight": [[frame, w], ...],             # 0 = keep the keyed erection curve, 1 = aim
   "smooth": 3,                             # +-frames of quaternion smoothing
   "entry_rest": [x,y,z], "entry_radius": 0.02,   # optional, preferred over vulva_verts:
                                            # her vaginal entrance in her mesh's rest space
   "canal_rest": [x,y,z]}                   # optional: canal direction, her rest space,
                                            # turned by her pelvis bone (else -skin normal)
The whole aim goes on penis_01 (the base joint), so the shaft stays straight and its
tip lands on the target line; the bend keys of penis_02..04 are faded out by the
same weight. "Inward" is from her vulva toward her pelvis bone, which is roughly the
vaginal axis on these rigs. Prints per-frame angle and reach for checking."""
import json, math, sys
import bpy
from mathutils import Quaternion, Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
CFG, OUT = ARGS
cfg = json.load(open(CFG))
G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]
P = bpy.data.objects["prostitute:CMovingPhysicalAgentComponent2_ARM"]
body = next(o for o in bpy.data.objects if o.type == "MESH" and cfg["body_mesh"] in o.name
)
CHAIN = ["penis_%02d" % k for k in range(1, 5)]
B, T = Vector(cfg["base"]), Vector(cfg["tip"])
r = (T - B).normalized()
length = (T - B).length
rest1 = G.data.bones[CHAIN[0]].matrix_local.to_quaternion()
pel_rest = G.data.bones["pelvis"].matrix_local
pts = cfg["weight"]


def weight(g):
    if g <= pts[0][0]:
        return pts[0][1]
    for (f0, a0), (f1, a1) in zip(pts, pts[1:]):
        if g <= f1:
            u = (g - f0) / max(1, f1 - f0)
            return a0 + (a1 - a0) * u * u * (3 - 2 * u)
    return pts[-1][1]


sc = bpy.context.scene
track = next(t for t in G.animation_data.nla_tracks if t.name.startswith("cutscene_anim_file"))
lo = min(int(round(s.frame_start)) for s in track.strips)
hi = max(int(round(s.frame_end)) for s in track.strips)

if "entry_rest" in cfg:
    e0 = Vector(cfg["entry_rest"])
    ring = [v.index for v in body.data.vertices if (v.co - e0).length < cfg.get("entry_radius", 0.02)]
    print("ENTRY ring", len(ring), "verts")

# Pass 1: the aim rotation per frame, in Geralt's rest space.
aims = {}
for g in range(lo, hi + 1):
    sc.frame_set(g)
    if "entry_rest" in cfg:
        # Skin vertices around her vaginal entrance (rest neighbourhood, symmetric), as the
        # game skins them; "inward" is against their mean surface normal.
        ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        vul = ev.matrix_world @ (sum((me.vertices[i].co for i in ring), Vector()) / len(ring))
        if "canal_rest" in cfg:
            # Direction from her pelvis bone's rotation; it is rigid, unlike the crotch skin.
            A = body.find_armature() or P
            hm = A.matrix_world @ A.pose.bones["pelvis"].matrix @ A.data.bones["pelvis"].matrix_local.inverted()
            inward = (hm.to_3x3() @ Vector(cfg["canal_rest"])).normalized()
        else:
            inward = -(ev.matrix_world.to_3x3() @ sum((me.vertices[i].normal for i in ring), Vector())).normalized()
        ev.to_mesh_clear()
    else:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(dg)
        me = ev.to_mesh()
        vul = ev.matrix_world @ (sum((me.vertices[i].co for i in cfg["vulva_verts"]), Vector())
                                 / len(cfg["vulva_verts"]))
        ev.to_mesh_clear()
        inward = ((P.matrix_world @ P.pose.bones["pelvis"].head) - vul).normalized()
    target = vul + inward * cfg["depth"]
    # Back into Geralt's rest space through his pelvis pose delta.
    pm = G.matrix_world @ G.pose.bones["pelvis"].matrix @ pel_rest.inverted()
    d = pm.inverted() @ target - B
    q = r.rotation_difference(d.normalized())
    ang = math.degrees(q.angle)
    if ang > cfg["max_deg"]:
        q = Quaternion().slerp(q, cfg["max_deg"] / ang)
    aims[g] = q
    if g % 15 == 0:
        e = pm.inverted() @ vul - B
        print("AIM f=%3d angle %5.1f entry at %.3f, target at %.3f (shaft %.3f) w %.2f"
              % (g, ang, e.length, d.length, length, weight(g)))

# Smooth so the aim does not jitter with the mesh.
k = cfg.get("smooth", 3)
sm = {}
for g in aims:
    acc = Vector((0, 0, 0, 0))
    ref = aims[g]
    for h in range(max(lo, g - k), min(hi, g + k) + 1):
        q = aims[h]
        v = Vector(q[:]) if q.dot(ref) >= 0 else -Vector(q[:])
        acc += v
    sm[g] = Quaternion(acc).normalized()

# Pass 2: rewrite the chain keys. penis_01 basis = rest^-1 * aim * rest, blended by weight
# with the keyed erection bend; the outer joints fade their bend out by the same weight.
for strip in track.strips:
    act = strip.action
    cb = act.layers[0].strips[0].channelbags[0] if hasattr(act, "layers") and act.layers else None
    fcs = cb.fcurves if cb else act.fcurves
    g0 = int(round(strip.frame_start))
    for n in CHAIN:
        path = 'pose.bones["%s"].rotation_quaternion' % n
        chans = sorted((fc for fc in fcs if fc.data_path == path), key=lambda fc: fc.array_index)
        assert len(chans) == 4, (strip.name, n)
        npts = len(chans[0].keyframe_points)
        cur = [[chans[i].keyframe_points[j].co[1] for i in range(4)] for j in range(npts)]
        for j in range(npts):
            g = min(hi, g0 + j)
            w = weight(g)
            keyed = Quaternion(cur[j])
            if n == CHAIN[0]:
                aim_local = rest1.inverted() @ sm[g] @ rest1
                new = keyed.slerp(aim_local, w)
            else:
                new = keyed.slerp(Quaternion(), w)
            for i in range(4):
                chans[i].keyframe_points[j].co[1] = new[i]
        for fc in chans:
            fc.update()
    print("STRIP", strip.name, "aimed")
bpy.ops.wm.save_as_mainfile(filepath=OUT)
