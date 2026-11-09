"""Headless: tilt the prostitute's pelvis so her vaginal canal points along Geralt's shaft.

  blender -b in.blend --python tilt_her.py -- tilt.json out.blend

tilt.json:
  {"body_mesh": "twals_03_wa__body",
   "entry_rest": [0, 0.035, 0.83], "entry_radius": 0.025,   # pivot: her vaginal entrance
   "canal_rest": [0, -0.27, 1],                              # canal direction, her rest space
   "base": [x,y,z], "tip": [x,y,z],                          # Geralt's shaft, his rest space
   "max_deg": 35,                                            # how much of the gap she takes
   "smooth": 15}                                             # +-frames of quaternion smoothing

After the retarget his shaft meets her canal 50-90 deg apart, tilted toward her belly, so
the aimed penis slid along her belly skin. Bending the penis that far looks broken; tilting
her pelvis (legs come up with it, as in missionary) takes part of the gap and aim_penis.py
the rest. The torso bone is re-solved to its old pose so her upper body stays on the bed.
Run before shift_her.py (which then places his base on the tilted canal axis)."""
import json, math, sys
import bpy
from mathutils import Matrix, Quaternion, Vector

CFG, OUT = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(CFG))
G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]
P = bpy.data.objects["prostitute:CMovingPhysicalAgentComponent2_ARM"]
body = next(o for o in bpy.data.objects if o.type == "MESH" and cfg["body_mesh"] in o.name)
B, T = Vector(cfg["base"]), Vector(cfg["tip"])
e0 = Vector(cfg["entry_rest"])
ring = [v.index for v in body.data.vertices if (v.co - e0).length < cfg["entry_radius"]]
sc = bpy.context.scene
track = next(t for t in P.animation_data.nla_tracks if t.name.startswith("cutscene_anim_file"))
lo = min(int(round(s.frame_start)) for s in track.strips)
hi = max(int(round(s.frame_end)) for s in track.strips)
pel, tor = P.pose.bones["pelvis"], P.pose.bones["torso"]


def canal_axis():
    hm = P.matrix_world @ pel.matrix @ P.data.bones["pelvis"].matrix_local.inverted()
    return (hm.to_3x3() @ Vector(cfg["canal_rest"])).normalized()


# Pass 1: per frame the world rotation taking her canal toward his shaft (clamped).
rot, piv = {}, {}
for g in range(lo, hi + 1):
    sc.frame_set(g)
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    piv[g] = ev.matrix_world @ (sum((me.vertices[i].co for i in ring), Vector()) / len(ring))
    ev.to_mesh_clear()
    gm = G.matrix_world @ G.pose.bones["pelvis"].matrix @ G.data.bones["pelvis"].matrix_local.inverted()
    q = canal_axis().rotation_difference((gm @ T - gm @ B).normalized())
    ang = math.degrees(q.angle)
    rot[g] = Quaternion().slerp(q, cfg["max_deg"] / ang) if ang > cfg["max_deg"] else q
k = cfg.get("smooth", 15)
sm = {}
for g in rot:
    acc = Vector((0, 0, 0, 0))
    for h in range(max(lo, g - k), min(hi, g + k) + 1):
        acc += Vector(rot[h][:]) if rot[h].dot(rot[g]) >= 0 else -Vector(rot[h][:])
    sm[g] = Quaternion(acc).normalized()

# Pass 2: new pelvis = pivot-rotated old pelvis; torso re-solved to its old armature pose.
to_arm = P.matrix_world.inverted()
vals = {}
for g in range(lo, hi + 1):
    sc.frame_set(g)
    p = to_arm @ piv[g]
    r = (to_arm.to_3x3() @ sm[g].to_matrix() @ P.matrix_world.to_3x3()).to_4x4()
    old_t = tor.matrix.copy()
    pel.matrix = Matrix.Translation(p) @ r @ Matrix.Translation(-p) @ pel.matrix
    bpy.context.view_layer.update()
    tor.matrix = old_t
    bpy.context.view_layer.update()
    vals[g] = (pel.location.copy(), pel.rotation_quaternion.copy(),
               tor.location.copy(), tor.rotation_quaternion.copy())
    if g % 30 == 0:
        print("TILT f=%3d %.1f deg" % (g, math.degrees(sm[g].angle)))

for strip in track.strips:
    act = strip.action
    cb = act.layers[0].strips[0].channelbags[0] if hasattr(act, "layers") and act.layers else None
    fcs = cb.fcurves if cb else act.fcurves
    g0 = int(round(strip.frame_start))
    for slot, bone, prop in ((0, "pelvis", "location"), (1, "pelvis", "rotation_quaternion"),
                             (2, "torso", "location"), (3, "torso", "rotation_quaternion")):
        path = 'pose.bones["%s"].%s' % (bone, prop)
        chans = sorted((fc for fc in fcs if fc.data_path == path), key=lambda fc: fc.array_index)
        for j in range(len(chans[0].keyframe_points)):
            v = vals[min(hi, g0 + j)][slot]
            for i, fc in enumerate(chans):
                fc.keyframe_points[j].co[1] = v[i]
        for fc in chans:
            fc.update()
    print("STRIP", strip.name, "tilted")

for g in range(lo, hi + 1, 30):
    sc.frame_set(g)
    gm = G.matrix_world @ G.pose.bones["pelvis"].matrix @ G.data.bones["pelvis"].matrix_local.inverted()
    print("CHECK f=%3d canal-shaft %.1f deg" % (g, math.degrees(canal_axis().angle(gm @ T - gm @ B))))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
