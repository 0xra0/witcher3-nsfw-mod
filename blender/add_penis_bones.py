"""Headless: give Geralt's cutscene armature the penis chain from a patched man_base rig
and key an erection curve on it.

  blender -b in.blend --python add_penis_bones.py -- man_base_penis.w2rig curve.json out.blend
curve.json: [[global_frame, bend_deg_per_joint], ...] (linear between points, eased);
negative bends down. The chain's rest (bone 0 angle) is the GeraltX erect shape.
Bones are appended to bone_order_list after the 94 rig bones, so their animation tracks
land on the same indices as in the patched rig (94..97)."""
import json, math, sys
import bpy
from mathutils import Quaternion
from bl_ext.user_default.witcher3_tools.importers import import_rig as ir

ARGS = sys.argv[sys.argv.index("--") + 1:]
RIG, CURVE, OUT = ARGS
G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]
CHAIN = ["penis_%02d" % k for k in range(1, 5)]

ref = ir.import_w3_rig(RIG, ns="penisref")
ref = ref if isinstance(ref, bpy.types.Object) else bpy.context.active_object
assert G.matrix_world == ref.matrix_world, "armatures not in the same space"
rest = {n: (ref.data.bones[n].head_local.copy(), ref.data.bones[n].tail_local.copy(),
            ref.data.bones[n].matrix_local.copy()) for n in CHAIN}
pel_ref, pel_g = ref.data.bones["pelvis"].matrix_local, G.data.bones["pelvis"].matrix_local
assert (pel_ref.translation - pel_g.translation).length < 1e-4, "pelvis rest differs"
bpy.data.objects.remove(ref)

bpy.context.view_layer.objects.active = G
for o in bpy.context.selected_objects:
    o.select_set(False)
G.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for n in CHAIN:
    if n in G.data.edit_bones:
        continue
    eb = G.data.edit_bones.new(n)
    eb.head, eb.tail = rest[n][0], rest[n][1]
    eb.matrix = rest[n][2]
    eb.parent = G.data.edit_bones["pelvis" if n == CHAIN[0] else CHAIN[CHAIN.index(n) - 1]]
bpy.ops.object.mode_set(mode="OBJECT")
order = G.data.witcherui_RigSettings.bone_order_list
have = [b.name for b in order]
for n in CHAIN:
    if n not in have:
        order.add().name = n
print("ORDER", len(order), [b.name for b in order][-5:])

pts = json.load(open(CURVE))
def bend(g):
    if g <= pts[0][0]:
        return pts[0][1]
    for (f0, a0), (f1, a1) in zip(pts, pts[1:]):
        if g <= f1:
            u = (g - f0) / max(1, f1 - f0)
            u = u * u * (3 - 2 * u)
            return a0 + (a1 - a0) * u
    return pts[-1][1]

track = next(t for t in G.animation_data.nla_tracks if t.name.startswith("cutscene_anim_file"))
for strip in track.strips:
    act = strip.action
    cb = act.layers[0].strips[0].channelbags[0] if hasattr(act, "layers") and act.layers else None
    fcs = cb.fcurves if cb else act.fcurves
    g0, g1 = int(round(strip.frame_start)), int(round(strip.frame_end))
    for n in CHAIN:
        pb = G.pose.bones[n]
        pb.rotation_mode = "QUATERNION"
        path = 'pose.bones["%s"]' % n
        for fc in [fc for fc in fcs if fc.data_path.startswith(path)]:
            fcs.remove(fc)
        span = range(g0, g1 + 1)
        vals = {"location": [(0.0, 0.0, 0.0)] * len(span),
                "rotation_quaternion": [tuple(Quaternion((0, 0, 1), math.radians(bend(g)))) for g in span]}
        for prop, n_ch in (("location", 3), ("rotation_quaternion", 4)):
            for i in range(n_ch):
                fc = fcs.new(path + "." + prop, index=i, group_name=n)
                fc.keyframe_points.add(len(span))
                co = []
                for k, v in enumerate(vals[prop]):
                    co += [float(k), float(v[i])]
                fc.keyframe_points.foreach_set("co", co)
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
                fc.update()
    print("STRIP", strip.name, g0, g1, "bend at start %.1f end %.1f" % (bend(g0), bend(g1)))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
