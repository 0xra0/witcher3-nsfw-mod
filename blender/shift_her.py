"""Headless: move the prostitute so her vulva sits on Geralt's penis, a fixed way up the shaft.

  blender -b in.blend --python shift_her.py -- shift.json out.blend

shift.json:
  {"body_mesh": "twals_03_wa__body",
   "entry_rest": [0, 0.035, 0.83], "entry_radius": 0.025,   # her vaginal entrance, mesh rest
   "base": [x,y,z], "tip": [x,y,z],                          # Geralt's shaft, his rest space
   "along": 0.04,                                            # entrance this far up the shaft
   "canal_rest": [0, -0.27, 1],                              # optional: put his base on her canal
                                                             # axis instead (use with aim_penis.py)
   "window_s": 1.0, "fps": 30}

retarget_slal.py's fit counts shaft samples inside her mesh, so a shaft buried in her
buttock or lower belly scores as well as one in the vulva (a raycast showed exactly that).
This pins the entrance itself: per frame, the translation that puts the skin around her
entrance (evaluated, so as the game skins it) on the shaft line. Averaging over about one
stroke keeps Geralt's thrust as in-and-out motion instead of gluing her to him. The shift
is added to her pelvis location keys, so it moves her whole body rigidly."""
import json, sys
import bpy
from mathutils import Matrix, Vector

CFG, OUT = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(CFG))
G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]
P = bpy.data.objects["prostitute:CMovingPhysicalAgentComponent2_ARM"]
body = next(o for o in bpy.data.objects if o.type == "MESH" and cfg["body_mesh"] in o.name)
B, T = Vector(cfg["base"]), Vector(cfg["tip"])
e0 = Vector(cfg["entry_rest"])
ring = [v.index for v in body.data.vertices if (v.co - e0).length < cfg["entry_radius"]]
print("SHIFT ring", len(ring), "verts")
sc = bpy.context.scene


def track(arm):
    return next(t for t in arm.animation_data.nla_tracks if t.name.startswith("cutscene_anim_file"))


lo = min(int(round(s.frame_start)) for s in track(P).strips)
hi = max(int(round(s.frame_end)) for s in track(P).strips)
raw = {}
for g in range(lo, hi + 1):
    sc.frame_set(g)
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    vul = ev.matrix_world @ (sum((me.vertices[i].co for i in ring), Vector()) / len(ring))
    ev.to_mesh_clear()
    gm = G.matrix_world @ G.pose.bones["pelvis"].matrix @ G.data.bones["pelvis"].matrix_local.inverted()
    b, t = gm @ B, gm @ T
    if "canal_rest" in cfg:
        # Put his base on her canal axis, "along" outside the entrance: aim_penis.py then
        # turns the shaft down the canal through the entrance. Pinning the entrance on his
        # current shaft instead left the base 5 cm off that axis, so the aimed shaft ran
        # along her belly skin.
        hm = P.matrix_world @ P.pose.bones["pelvis"].matrix @ P.data.bones["pelvis"].matrix_local.inverted()
        canal = (hm.to_3x3() @ Vector(cfg["canal_rest"])).normalized()
        raw[g] = b + canal * cfg["along"] - vul
    else:
        raw[g] = b + (t - b).normalized() * cfg["along"] - vul
half = int(cfg["window_s"] * cfg["fps"] / 2)
shift = {g: sum((raw[h] for h in range(max(lo, g - half), min(hi, g + half) + 1)), Vector())
         / (min(hi, g + half) - max(lo, g - half) + 1) for g in raw}
for g in range(lo, hi + 1, 30):
    print("SHIFT f=%3d raw %.3f smoothed %.3f" % (g, raw[g].length, shift[g].length))

# Add the world shift to her pelvis: new pose matrix = T(shift in armature space) @ old.
pb = P.pose.bones["pelvis"]
to_arm = P.matrix_world.to_3x3().inverted()
new_loc = {}
for g in range(lo, hi + 1):
    sc.frame_set(g)
    m = Matrix.Translation(to_arm @ shift[g]) @ pb.matrix
    new_loc[g] = P.convert_space(pose_bone=pb, matrix=m, from_space="POSE", to_space="LOCAL").to_translation()
for strip in track(P).strips:
    act = strip.action
    cb = act.layers[0].strips[0].channelbags[0] if hasattr(act, "layers") and act.layers else None
    fcs = cb.fcurves if cb else act.fcurves
    g0 = int(round(strip.frame_start))
    chans = sorted((fc for fc in fcs if fc.data_path == 'pose.bones["pelvis"].location'),
                   key=lambda fc: fc.array_index)
    assert len(chans) == 3, strip.name
    for j in range(len(chans[0].keyframe_points)):
        g = min(hi, g0 + j)
        for i in range(3):
            chans[i].keyframe_points[j].co[1] = new_loc[g][i]
    for fc in chans:
        fc.update()
    print("STRIP", strip.name, "shifted")

# Check: entrance distance from the shaft line after the shift.
for g in range(lo, hi + 1, 30):
    sc.frame_set(g)
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    vul = ev.matrix_world @ (sum((me.vertices[i].co for i in ring), Vector()) / len(ring))
    ev.to_mesh_clear()
    gm = G.matrix_world @ G.pose.bones["pelvis"].matrix @ G.data.bones["pelvis"].matrix_local.inverted()
    b, t = gm @ B, gm @ T
    ax = (t - b).normalized()
    a = (vul - b).dot(ax)
    print("CHECK f=%3d entrance along %.3f perp %.3f" % (g, a, ((vul - b) - ax * a).length))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
