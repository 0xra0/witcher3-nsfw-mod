"""Headless: her mouth opens round the shaft (oral), as mimic pose weights in the face strips.

  blender -b in.blend --python face_her.py -- face.json out.blend

face.json:
  {"shaft_len": 0.16,          # GeraltX mesh shaft from penis_01, metres (glans tip)
   "ramp": 0.02,               # lips this far inside the tip = fully open
   "weights": {"jaw_open_o": [0.25, 0.9], "jaw_open_a": [0.2, 0.15]},   # [lips off, lips on]
   "smooth": 2}

W3 faces are posed by weighted mimic poses, not by the jaw bone. The cutscene keeps them
as float curves on the w3_face_poses bone in each actor's cutscene_anim_face* strips; the
vanilla scene holds jaw_open_a ~0.2. Per frame this measures how far her lips sit inside the
glans tip (run after mouth_her.py) and blends each weight from "off" to "on"."""
import json, os, sys
import bpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nla_keys import _fcurves, frame_range, smooth_list

CFG, OUT = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(CFG))
P = bpy.data.objects["prostitute:CMovingPhysicalAgentComponent2_ARM"]
G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]
M = bpy.data.objects["prostitute:CMimicComponent12_ARM"]
sc = bpy.context.scene
lo, hi = frame_range(P)
frames = list(range(lo, hi + 1))
W = lambda A, n, t=False: A.matrix_world @ (A.pose.bones[n].tail if t else A.pose.bones[n].head)

inside = []
for g in frames:
    sc.frame_set(g)
    b = W(G, "penis_01")
    ax = (W(G, "penis_04", True) - b).normalized()
    lip = (W(M, "upper_lip") + W(M, "lowwer_lip")) / 2
    k = (cfg["shaft_len"] - (lip - b).dot(ax)) / cfg["ramp"]
    inside.append(min(1.0, max(0.0, k)))
inside = smooth_list(inside, cfg.get("smooth", 2))

face = next(t for t in P.animation_data.nla_tracks if t.name.startswith("cutscene_anim_face"))
for name, (off, on) in cfg["weights"].items():
    path = 'pose.bones["w3_face_poses"]["%s"]' % name
    # Rekey every frame: a vanilla curve may hold one key per strip (jaw_open_o does).
    n = 0
    for strip in face.strips:
        fc = next(f for f in _fcurves(strip.action) if f.data_path == path)
        while fc.keyframe_points:
            fc.keyframe_points.remove(fc.keyframe_points[0], fast=True)
        for a in range(int(round(strip.action_frame_start)), int(round(strip.action_frame_end)) + 1):
            g = int(round(strip.frame_start + (a - strip.action_frame_start) * strip.scale))
            k = inside[min(hi, max(lo, g)) - lo]
            fc.keyframe_points.insert(a, off + k * (on - off), options={"FAST"}).interpolation = "LINEAR"
            n += 1
        fc.update()
    print("FACE %s %d keys, %.2f..%.2f" % (name, n, off, on))
print("FACE lips inside the tip on %d of %d frames (k>0.5)" % (sum(k > 0.5 for k in inside), len(inside)))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
