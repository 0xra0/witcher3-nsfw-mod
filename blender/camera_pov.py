"""Headless: Geralt's first-person view. The cutscene camera rides his eyes and looks at her crotch.

  blender -b scene.blend --python camera_pov.py -- pov.json out.blend

pov.json:
  {"eye": [0.14, 0.18],        # from his neck bone: up (world Z), forward (level, toward her)
   "target_rest": [0, 0.036, 0.921], "target_radius": 0.025,   # her vulva, rest space
   "target_lift": [0, 0, 0.05], # world offset
   "toward_head": 0.3,          # slide the aim this fraction of the way from her vulva to her neck
   "eye_smooth_s": 0.6, "target_smooth_s": 0.4,
   "leg_clear": 0.45,           # lift the eye to keep her shins/feet this far away (near plane)
   "smooth_passes": 1,          # >1 repeats the box smoothing (2 = triangle window, kills the thrust sway)
   "lift_after_smooth": false,  # true: smooth the eye first, then lift for leg_clear (envelope-smoothed)
   "fov": 70,  # the game reads hctFOV as VERTICAL degrees
   "close": {"dir": [0.5, 0.3, 1.0],   # optional close-up shots on her entrance: direction in her
             "dist": 0.6, "fov": 25,   #   pelvis rest frame as (side, out of the canal, front)
             "shots": [[130, 260], [390, 440, {"dir": [0.8, 0.2, 1]}]],  # [first, last, overrides]
             "blend_s": 1.0, "smooth_s": 0.4,
             "head_clear": 0.5,            # keep the eye this far from his head (the game hides him)
             "limb_clear": 0.4,            # ... and from her thigh/shin/foot bones
             "arm_clear": 0.35}}           # ... and from his arms (they hold her thighs)

The eye sits in front of his face, outside his head and torso meshes;
smoothing the eye takes out the head bob a rigid head-cam would pass straight on.
The view direction ignores his head rotation and always aims at the target.

From his eyes the canal runs almost along the line of sight, so the in/out stroke and the
lips' tug move toward the lens and can't be seen. The close-up shots glide the camera
from his eyes to a point above her hip that looks across the canal, hold, and glide back
(eye, aim, roll and FOV all blend with one smoothstep weight).
"""
import json
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import entrance_bones as eb
from camera_track import CAMERA_BONE, CAMERA_RIG, DOF, camera_object, key_camera, smooth

GERALT = "geralt:CMovingPhysicalAgentComponent25_ARM"
HER = "prostitute:CMovingPhysicalAgentComponent2_ARM"
BODY = "twals_03_wa__body"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    cfg = json.load(open(argv[0]))
    scene = bpy.context.scene
    rig = bpy.data.objects[CAMERA_RIG]
    cam = camera_object(rig)
    pb = rig.pose.bones[CAMERA_BONE]
    G = bpy.data.objects[GERALT]
    P = bpy.data.objects[HER]
    body = next(o for o in bpy.data.objects if o.type == "MESH" and BODY in o.name)
    t0 = Vector(cfg["target_rest"])
    ring = [v.index for v in body.data.vertices if (v.co - t0).length < cfg["target_radius"]]

    scene.frame_set(scene.frame_start)
    rel = (rig.matrix_world @ pb.matrix).inverted() @ cam.matrix_world
    rest_cn = rig.data.bones[CAMERA_BONE].matrix_local

    up, fwd = cfg["eye"]
    eyes, tgts, ups = [], [], []
    ccfg = cfg.get("close")
    c_eyes, c_tgts, heads, her_limbs, his_arms = [], [], [], [], []
    checks = []
    for f in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(f)
        ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        v = ev.matrix_world @ (sum((me.vertices[i].co for i in ring), Vector()) / len(ring))
        # Eye from his neck, not the head bone: a head-bone offset landed 10 cm behind the
        # neck, inside his torso, which the game then culls (only his open waist showed).
        # Forward over a long baseline (his pelvis -> her neck, ~0.9 m): neck -> vulva is only
        # ~0.2 m level, so a few cm of her hip sway swung the eye 15 cm sideways.
        gneck = G.matrix_world @ G.pose.bones["neck"].head
        h = (P.matrix_world @ P.pose.bones["neck"].head) - (G.matrix_world @ G.pose.bones["pelvis"].head)
        h.z = 0
        eye = gneck + h.normalized() * fwd + Vector((0, 0, up))
        # The game's near plane is ~0.3 m: in stage 2 her feet rise beside his head and the
        # shins, running toward the lens, were clipped to hollow stumps at the knee. Lift the
        # eye until every point along her shins and feet near the view cone is leg_clear deep.
        clear = cfg.get("leg_clear", 0.0)
        legs = []
        for s in "lr":
            k = P.matrix_world @ P.pose.bones[s + "_shin"].head
            a = P.matrix_world @ P.pose.bones[s + "_foot"].head
            legs += [k.lerp(a, i / 10) for i in range(11)]
        tgt = v.lerp(P.matrix_world @ P.pose.bones["neck"].head, cfg.get("toward_head", 0.0))

        def too_close(eye, tgt=tgt, legs=legs):
            d = (tgt - eye).normalized()
            for p in legs:
                r = p - eye
                depth = r.dot(d)
                # 1.4 = tan of the 16:9 half-diagonal (~50 deg) plus margin: farther out is off-screen
                if 0 < depth < clear and (r - d * depth).length < 1.4 * depth + 0.1:
                    return True
            return False

        if cfg.get("lift_after_smooth"):
            checks.append(too_close)
        else:
            while clear and too_close(eye):
                eye.z += 0.01
        eyes.append(eye)
        ups.append(h.normalized())
        neck = P.matrix_world @ P.pose.bones["neck"].head
        tgts.append(v.lerp(neck, cfg.get("toward_head", 0.0)))
        heads.append(G.matrix_world @ G.pose.bones["head"].head)
        limbs = []
        for sd in "lr":
            chain = [P.matrix_world @ P.pose.bones[sd + b].head for b in ("_thigh", "_shin", "_foot")]
            limbs += [a.lerp(b, i / 6) for a, b in zip(chain, chain[1:]) for i in range(7)]
        her_limbs.append(limbs)
        arms = []
        for sd in "lr":
            chain = [G.matrix_world @ G.pose.bones[sd + b].head for b in ("_bicep", "_forearm", "_hand", "_middle1")]
            arms += [a.lerp(b, i / 6) for a, b in zip(chain, chain[1:]) for i in range(7)]
        arms += [G.matrix_world @ G.pose.bones[b].head for b in ("pelvis", "torso", "torso2", "torso3", "neck")
                 if b in G.pose.bones]
        his_arms.append(arms)
        if ccfg:
            # her pelvis rotation applied to the rest-frame direction (side, out, front)
            R = (P.matrix_world @ P.pose.bones["pelvis"].matrix @ P.data.bones["pelvis"].matrix_local.inverted()).to_3x3().normalized()
            row = []
            for shot in ccfg["shots"]:
                o = dict(ccfg, **(shot[2] if len(shot) > 2 else {}))
                a, b, c = o["dir"]
                w = (R @ (Vector(eb.SIDE) * a - Vector(eb.CANAL) * b + Vector(eb.FRONT) * c)).normalized()
                row.append(v + w * o["dist"])
            c_eyes.append(row)
            c_tgts.append(v.copy())
        ev.to_mesh_clear()

    fps = scene.render.fps / scene.render.fps_base
    passes = cfg.get("smooth_passes", 1)
    for _ in range(passes):
        eyes = smooth(eyes, int(cfg.get("eye_smooth_s", 0.6) * fps / 2))
        tgts = smooth(tgts, int(cfg.get("target_smooth_s", 0.4) * fps / 2))
    if checks:
        # Lift after smoothing: lifting first and then smoothing averaged the lift away right
        # where her legs come up. Running max then box with the same half-width never drops
        # below the per-frame need (every box window lies inside each frame's max window).
        need = []
        for eye, tgt, too_close in zip(eyes, tgts, checks):
            z = 0.0
            while too_close(eye + Vector((0, 0, z)), tgt):
                z += 0.01
            need.append(z)
        k = int(cfg.get("lift_smooth_s", 1.0) * fps / 2)
        peak = [max(need[max(0, i - k):i + k + 1]) for i in range(len(need))]
        lifts = [sum(peak[max(0, i - k):i + k + 1]) / len(peak[max(0, i - k):i + k + 1]) for i in range(len(peak))]
        eyes = [e + Vector((0, 0, z)) for e, z in zip(eyes, lifts)]
        print("POV lift after smooth: max %.2f m" % max(lifts))
    lift = Vector(cfg.get("target_lift", (0, 0, 0)))
    tgts = [p + lift for p in tgts]

    basis = []
    ups = smooth(ups, int(fps))
    n = len(eyes)
    fovs = [float(cfg["fov"])] * n
    if ccfg:
        k = int(ccfg.get("smooth_s", 0.4) * fps / 2)
        shots = ccfg["shots"]
        per_shot = [[row[j] for row in c_eyes] for j in range(len(shots))]
        for _ in range(passes):
            per_shot = [smooth(p, k) for p in per_shot]
            c_tgts = smooth(c_tgts, k)
        ramp = int(ccfg.get("blend_s", 1.0) * fps)   # 0: hard cut in and out
        wts, c_eyes = [0.0] * n, [None] * n
        for j, shot in enumerate(shots):
            a, b = shot[:2]
            for i in range(n):
                f = i + scene.frame_start
                if a <= f <= b:
                    x = 1.0
                else:
                    x = max(0.0, 1 - (a - f) / ramp if f < a else 1 - (f - b) / ramp) if ramp else 0.0
                x = x * x * (3 - 2 * x)
                if x > wts[i]:
                    wts[i], c_eyes[i] = x, per_shot[j][i]
        for i, w in enumerate(wts):
            if w:
                eyes[i] = eyes[i].lerp(c_eyes[i], w)
                tgts[i] = tgts[i].lerp(c_tgts[i], w)
                # image-up stays his level forward (her head at the top): the close-up also
                # looks mostly down, where a world-up hint would roll the picture
                fovs[i] += (float(ccfg["fov"]) - fovs[i]) * w
                # The straight glide skims his head and cuts through her thigh: push the eye
                # out of a ball round his head (the game hides him inside ~0.4 m) and round
                # her leg bones (limb radius + the ~0.3 m near plane).
                obst = [(heads[i], ccfg.get("head_clear", 0.5))] + \
                       [(q, ccfg.get("limb_clear", 0.4)) for q in her_limbs[i]] + \
                       [(q, ccfg.get("arm_clear", 0.35)) for q in his_arms[i]]
                for _ in range(20):
                    hit = False
                    for q, rad in obst:
                        r = eyes[i] - q
                        if r.length < rad:
                            eyes[i] = q + r.normalized() * rad
                            hit = True
                    if not hit:
                        break
        # the push follows his bob; ease it, but never across a cut
        cuts = [0] + [i for i in range(1, n) if (eyes[i] - eyes[i - 1]).length > 0.1] + [n]
        eyes = [e for u, v in zip(cuts, cuts[1:]) for e in smooth(eyes[u:v], int(0.2 * fps / 2))]
        # the game hides Geralt when the camera is within ~0.4 m of his head (v8pov2)
        for shot in ccfg["shots"]:
            a, b = shot[:2]
            span = [i for i in range(n) if wts[i] > 0 and a - ramp <= i + scene.frame_start <= b + ramp]
            dh = min(((eyes[i] - heads[i]).length, i + scene.frame_start) for i in span)
            dl = min((min((eyes[i] - q).length for q in her_limbs[i]), i + scene.frame_start) for i in span)
            print("POV close-up %d-%d: min dist to his head %.2f at f%d, to her leg bones %.2f at f%d" % ((a, b) + dh + dl))
    for pos, tgt, hup in zip(eyes, tgts, ups):
        # Roll: image-up = his level forward (toward her head). He looks nearly straight down,
        # where track_quat's world-up is degenerate and the picture spun.
        d = (tgt - pos).normalized()
        y = (hup - d * hup.dot(d)).normalized()
        cam_world = Matrix((y.cross(-d), y, -d)).transposed().to_4x4()
        cam_world.translation = pos
        basis.append(rest_cn.inverted() @ (rig.matrix_world.inverted() @ cam_world @ rel.inverted()))

    key_camera(rig, basis, dict(DOF, hctFOV=fovs, dofFocusDistNear=0.3,
                                dofFocusDistFar=1.5, **cfg.get("dof", {})))
    for f in (scene.frame_start, 200, 300):
        scene.frame_set(f)
        print("POV f=%d eye %s tgt %s dist %.2f" % (f, tuple(round(c, 2) for c in cam.matrix_world.translation),
              tuple(round(c, 2) for c in tgts[f - scene.frame_start]),
              (cam.matrix_world.translation - tgts[f - scene.frame_start]).length))
    bpy.ops.wm.save_as_mainfile(filepath=argv[1])


if __name__ == "__main__":
    main()
