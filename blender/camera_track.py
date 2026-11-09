"""Headless: replace the cutscene camera with one slow arc that frames both actors.

  blender -b scene.blend --python camera_track.py -- camera.json out.blend

camera.json:
  {"radius": 1.6,            # metres from the look-at point (horizontal)
   "azimuth": [200, 150],    # degrees around +Z, 0 = +X; start -> end, eased
   "height": [1.45, 1.55],   # camera Z, start -> end
   "fov": 60,                # hctFOV written to Camera_Node
   "smooth_s": 2.0,          # look-at point = moving average over this window
   "target_offset": [0, 0, 0.1],   # added to the look-at point
   "dof": {"dofFocusDistNear": 1.0, ...}}   # optional overrides

The vanilla camera is five telephoto shots (hctFOV ~10) aimed where the vanilla
actors were, joined by fade events. A retargeted animation lives somewhere else,
so the shots frame empty bed. This keys a single continuous camera instead.

Only Camera_Node moves; the orbit/look-at/manipulation bones stay at rest. Keys
go into each NLA strip of the camera track, like retarget_slal.py does for the
actors, so the exporter's strip-based cut segments stay intact.
"""
import json
import math
import sys

import bpy
from mathutils import Matrix, Vector

CAMERA_RIG = "camera:CAnimatedComponent2_ARM"
CAMERA_BONE = "Camera_Node"
ACTOR_RIGS = ("geralt:CMovingPhysicalAgentComponent25_ARM",
              "prostitute:CMovingPhysicalAgentComponent2_ARM")
LOOK_BONES = ("pelvis", "head")
DOF = {"overrideFactor": 1.0, "dofIntensity": 0.3,
       "dofBlurDistNear": 0.5, "dofFocusDistNear": 1.0,
       "dofFocusDistFar": 2.4, "dofBlurDistFar": 4.5}


def camera_object(rig):
    return next(o for o in bpy.data.objects
                if o.type == "CAMERA" and o.parent == rig and o.parent_bone == CAMERA_BONE)


def look_targets(scene):
    """Per-frame mean of both actors' pelvis and head, moving-averaged."""
    raw = []
    for f in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(f)
        pts = [bpy.data.objects[r].matrix_world @ bpy.data.objects[r].pose.bones[b].head
               for r in ACTOR_RIGS for b in LOOK_BONES]
        raw.append(sum(pts, Vector()) / len(pts))
    return raw


def smooth(points, half):
    out = []
    for i in range(len(points)):
        win = points[max(0, i - half):i + half + 1]
        out.append(sum(win, Vector()) / len(win))
    return out


def ease(t):
    return t * t * (3 - 2 * t)


def channelbag(action):
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                return cb
    raise RuntimeError("action %s has no channelbag" % action.name)


def key_camera(rig, basis, props):
    """Write basis[frame] (Camera_Node matrices) and the Camera_Node props into every camera strip."""
    n = len(basis)
    track = next(t for t in rig.animation_data.nla_tracks if t.name.startswith("cutscene_anim_file"))
    for strip in track.strips:
        cb = channelbag(strip.action)
        for fc in [fc for fc in cb.fcurves if fc.data_path.startswith("pose.bones")]:
            cb.fcurves.remove(fc)
        g0, g1 = int(round(strip.frame_start)), int(round(strip.frame_end))
        span = [min(g, n - 1) for g in range(g0, g1 + 1)]
        for bone in rig.data.bones:
            path = 'pose.bones["%s"]' % bone.name
            rig.pose.bones[bone.name].rotation_mode = "QUATERNION"
            if bone.name == CAMERA_BONE:
                mats = [basis[g] for g in span]
            else:
                mats = [Matrix.Identity(4)] * len(span)
            quats, prev = [], None
            for m in mats:
                q = m.to_quaternion()
                if prev is not None and q.dot(prev) < 0:
                    q.negate()
                prev = q
                quats.append(q)
            channels = [("location", i, [m.translation[i] for m in mats]) for i in range(3)]
            channels += [("rotation_quaternion", i, [q[i] for q in quats]) for i in range(4)]
            if bone.name == CAMERA_BONE:
                # a prop is one value for the whole scene, or a list with one value per frame
                channels += [('["%s"]' % k, 0, [v[g] for g in span] if isinstance(v, list) else [v] * len(span))
                             for k, v in props.items()]
            for prop, idx, vals in channels:
                dp = path + ("." + prop if not prop.startswith("[") else prop)
                fc = cb.fcurves.new(dp, index=idx, group_name=bone.name)
                fc.keyframe_points.add(len(vals))
                co = []
                for k, v in enumerate(vals):
                    co += [float(k), float(v)]
                fc.keyframe_points.foreach_set("co", co)
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
                fc.update()
    for k, v in props.items():
        rig.pose.bones[CAMERA_BONE][k] = v[0] if isinstance(v, list) else v


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    cfg = json.load(open(argv[0]))
    scene = bpy.context.scene
    rig = bpy.data.objects[CAMERA_RIG]
    cam = camera_object(rig)
    pb = rig.pose.bones[CAMERA_BONE]

    # Constant bone -> camera-object offset (bone tail + import-time axis fix).
    scene.frame_set(scene.frame_start)
    rel = (rig.matrix_world @ pb.matrix).inverted() @ cam.matrix_world
    rest_cn = rig.data.bones[CAMERA_BONE].matrix_local

    fps = scene.render.fps / scene.render.fps_base
    lift = Vector(cfg.get("target_offset", (0, 0, 0)))
    targets = [p + lift for p in smooth(look_targets(scene), int(cfg.get("smooth_s", 2.0) * fps / 2))]
    n = len(targets)
    a0, a1 = (math.radians(a) for a in cfg["azimuth"])
    z0, z1 = cfg["height"]
    radius = cfg["radius"]

    basis = []
    for i, tgt in enumerate(targets):
        t = ease(i / max(1, n - 1))
        az = a0 + (a1 - a0) * t
        pos = Vector((tgt.x + radius * math.cos(az), tgt.y + radius * math.sin(az), z0 + (z1 - z0) * t))
        cam_world = (tgt - pos).to_track_quat("-Z", "Y").to_matrix().to_4x4()
        cam_world.translation = pos
        bone_arm = rig.matrix_world.inverted() @ cam_world @ rel.inverted()
        basis.append(rest_cn.inverted() @ bone_arm)

    props = dict(DOF, hctFOV=float(cfg["fov"]), **cfg.get("dof", {}))
    key_camera(rig, basis, props)

    scene.frame_set(scene.frame_start)
    print("CAMERA frames=%d start=%s end=%s fov=%s" % (
        n, tuple(round(x, 2) for x in cam.matrix_world.translation),
        tuple(round(x, 2) for x in targets[0]), cfg["fov"]))
    bpy.ops.wm.save_as_mainfile(filepath=argv[1])


if __name__ == "__main__":
    main()
