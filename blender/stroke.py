"""Headless: give the penetration real in-and-out strokes.

  blender -b in.blend --python stroke.py -- stroke.json out.blend

stroke.json:
  {"body_mesh": "twals_03_wa__body", "entry_rest": [0, 0.036, 0.921], "entry_radius": 0.014,
   "base": [x,y,z], "tip": [x,y,z],      # his shaft, his rest space (as shift_her.py)
   "canal_rest": [0, -0.3, 1],
   "depth": [0.045, 0.13],               # shaft inside her: out-stroke .. in-stroke (m)
   "him_share": 0.6,                     # of each correction, how much moves him (rest: her)
   "window_s": 1.2}                      # running min/max for the thrust phase (>= 1 stroke)

The SLAL animation moves her with him (she rocks with every thrust) and shift_her.py then
pinned her entrance to a fixed point on the shaft, so the depth varied by less than 1 cm:
it read as two bodies glued together. Here the depth follows his thrust phase instead,
from his pelvis travelling toward her head (running min/max -> 0..1, so each stage's own
stroke amplitude and tempo are kept). Run after shift_her.py and before aim_penis.py: the
base stays on her canal axis, only its distance along the axis changes."""
import json, sys
import bpy
from mathutils import Matrix, Vector
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nla_keys import frame_range, local_of, smooth_list, write

CFG, OUT = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(CFG))
G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]
P = bpy.data.objects["prostitute:CMovingPhysicalAgentComponent2_ARM"]
body = next(o for o in bpy.data.objects if o.type == "MESH" and cfg["body_mesh"] in o.name)
B, T = Vector(cfg["base"]), Vector(cfg["tip"])
L = (T - B).length
e0 = Vector(cfg["entry_rest"])
ring = [v.index for v in body.data.vertices if (v.co - e0).length < cfg["entry_radius"]]
sc = bpy.context.scene
lo, hi = frame_range(P)
frames = list(range(lo, hi + 1))


def pelvis_world(A):
    return A.matrix_world @ A.pose.bones["pelvis"].matrix @ A.data.bones["pelvis"].matrix_local.inverted()


thrust, along, canal = [], [], []
for g in frames:
    sc.frame_set(g)
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    vul = ev.matrix_world @ (sum((me.vertices[i].co for i in ring), Vector()) / len(ring))
    ev.to_mesh_clear()
    c = (pelvis_world(P).to_3x3() @ Vector(cfg["canal_rest"])).normalized()
    b = pelvis_world(G) @ B
    ax = (P.matrix_world @ P.pose.bones["neck"].head) - (P.matrix_world @ P.pose.bones["pelvis"].head)
    ax.z = 0
    thrust.append((G.matrix_world @ G.pose.bones["pelvis"].head).dot(ax.normalized()))
    along.append((vul - b).dot(c))
    canal.append(c)

fps = sc.render.fps / sc.render.fps_base
half = int(cfg.get("window_s", 1.2) * fps / 2)
phase = []
for i in range(len(frames)):
    w = thrust[max(0, i - half):i + half + 1]
    mn, mx = min(w), max(w)
    phase.append(0.5 if mx - mn < 0.005 else (thrust[i] - mn) / (mx - mn))
# The running window squares off the ends of each stroke; a short smooth rounds them again.
phase = smooth_list(phase, 2)
d0, d1 = cfg["depth"]
share = cfg.get("him_share", 0.6)
delta = {}
for i, g in enumerate(frames):
    want = L - (d0 + (d1 - d0) * phase[i])        # base -> entrance distance along the canal
    delta[g] = (want - along[i]) * canal[i]       # >0: pull apart
for g in frames[::15]:
    i = g - lo
    print("STROKE f=%3d phase %.2f depth %.3f -> %.3f" % (g, phase[i], L - along[i], d0 + (d1 - d0) * phase[i]))


def move(A, sign_share):
    pb = A.pose.bones["pelvis"]
    to_arm = A.matrix_world.to_3x3().inverted()
    loc = {}
    for g in frames:
        sc.frame_set(g)
        m = Matrix.Translation(to_arm @ (delta[g] * sign_share)) @ pb.matrix
        loc[g] = local_of(A, pb, m).to_translation()
    write(A, "pelvis", "location", loc)


move(G, -share)          # his base backs out along the canal
move(P, 1 - share)       # her entrance moves on along it

ev_d = []
for g in frames[::30]:
    sc.frame_set(g)
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    vul = ev.matrix_world @ (sum((me.vertices[i].co for i in ring), Vector()) / len(ring))
    ev.to_mesh_clear()
    c = (pelvis_world(P).to_3x3() @ Vector(cfg["canal_rest"])).normalized()
    ev_d.append("%d:%.3f" % (g, L - (vul - pelvis_world(G) @ B).dot(c)))
print("CHECK depth", " ".join(ev_d))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
