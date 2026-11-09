"""Headless: replace the in/out depth inside a frame window with a steady, designed rhythm.

  blender -b in.blend --python restroke.py -- restroke.json out.blend

restroke.json: the stroke.json keys (body_mesh, entry_rest, entry_radius, base, tip,
canal_rest, depth, him_share) plus
   "window": [a, a_full, b_full, b],    # frames: blend in over a..a_full, out over b_full..b
   "period_s": 0.6,                     # one stroke
   "push": 0.4}                         # share of the cycle spent going in (rest: pulling out)

stroke.py takes the depth from his own thrust phase, which works in stage 1 (a clean 40-frame
SLAL loop). The stage-2 SLAL clip has no real thrust (his pelvis moves ~1 cm, irregularly),
so there the depth just hovered round 9 cm, right in the close-up. Here the depth follows a
designed cycle instead: a quicker push in, a slower pull out, full stroke length. Same
correction split as stroke.py (him_share on his pelvis, the rest on hers, along her canal).
Run on a finished blend, then re-run bend_penis, hands_her, open_entrance (rekey_only) and
camera_pov, which all recompute every frame from the poses."""
import json, os, sys
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nla_keys import frame_range, local_of, write

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
fps = sc.render.fps / sc.render.fps_base
lo, hi = frame_range(P)
a, a1, b1, b = cfg["window"]
frames = list(range(max(lo, a), min(hi, b) + 1))


def pelvis_world(A):
    return A.matrix_world @ A.pose.bones["pelvis"].matrix @ A.data.bones["pelvis"].matrix_local.inverted()


def measure():
    along, canal = [], []
    for g in frames:
        sc.frame_set(g)
        ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        vul = ev.matrix_world @ (sum((me.vertices[i].co for i in ring), Vector()) / len(ring))
        ev.to_mesh_clear()
        c = (pelvis_world(P).to_3x3() @ Vector(cfg["canal_rest"])).normalized()
        along.append((vul - pelvis_world(G) @ B).dot(c))
        canal.append(c)
    return along, canal


def ss(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def cycle(u):
    """0 (out) .. 1 (in) over one stroke, u in [0,1): eased push, then eased pull."""
    p = cfg.get("push", 0.4)
    return ss(u / p) if u < p else 1.0 - ss((u - p) / (1.0 - p))


def weight(g):
    return ss((g - a) / max(1, a1 - a)) * (1.0 - ss((g - b1) / max(1, b - b1)))


along, canal = measure()
d0, d1 = cfg["depth"]
per = cfg["period_s"] * fps
# Phase chosen so the cycle is fully out where the blend starts (the transition pose).
want = {g: d0 + (d1 - d0) * cycle(((g - a) / per) % 1.0) for g in frames}
share = cfg.get("him_share", 0.6)
delta = {}
for i, g in enumerate(frames):
    cur = L - along[i]
    tgt = cur + weight(g) * (want[g] - cur)
    delta[g] = ((L - tgt) - along[i]) * canal[i]          # >0: pull apart


def move(A, sign_share):
    pb = A.pose.bones["pelvis"]
    to_arm = A.matrix_world.to_3x3().inverted()
    loc = {}
    for g in frames:
        sc.frame_set(g)
        m = Matrix.Translation(to_arm @ (delta[g] * sign_share)) @ pb.matrix
        loc[g] = local_of(A, pb, m).to_translation()
    write(A, "pelvis", "location", loc)


move(G, -share)
move(P, 1 - share)

after, _ = measure()
print("RESTROKE period %.1f frames, window %s" % (per, cfg["window"]))
for i in range(0, len(frames), 6):
    g = frames[i]
    print("RESTROKE f=%3d w %.2f want %.3f got %.3f" % (g, weight(g), want[g], L - after[i]))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
