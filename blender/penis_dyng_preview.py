"""Blender preview of the penis dangle presets (tools/penis_dyng.py) on the live rig.

Run inside Blender with the live man_base rig (armature ARM) and Geralt's re-skinned
l_01_mg__body mesh loaded. Keys a walk-then-jump pelvis motion, then a Verlet chain on
penis_02..penis_05_null with the dyng node semantics as read from game data: a node with
distance 0 is pinned to its animated pose; others are pulled toward it by stiffness,
fall under gravity, stay within `distance` of it, and links keep segment lengths.
This approximates the engine's solver for tuning; it is not the solver itself.
"""
import math
import bpy
from mathutils import Matrix, Vector

CHAIN = ["penis_01", "penis_02", "penis_03", "penis_04"]

def key_motion(arm, frames, fps):
    pb = arm.pose.bones["pelvis"]; pb.rotation_mode = "XYZ"
    for f in range(frames + 1):
        t = f / fps
        if t < 2.0:   # walk: 2 steps/s vertical bob, 1 Hz side sway and yaw
            z = 0.025 * math.sin(2 * math.pi * 2 * t); x = 0.02 * math.sin(2 * math.pi * t); yaw = math.radians(4) * math.sin(2 * math.pi * t)
        else:         # jump: up 0.25 m and back down by t = 2.6 s, then still
            u = min(t - 2.0, 0.6) / 0.6; z = 0.25 * 4 * u * (1 - u); x = 0.0; yaw = 0.0
        # pose-space offset in armature axes, converted into the bone's basis
        world = Matrix.Translation((x, 0, z)) @ Matrix.Rotation(yaw, 4, "Z")
        rest = arm.data.bones["pelvis"].matrix_local
        pb.matrix_basis = rest.inverted() @ world @ rest
        pb.keyframe_insert("location", frame=f); pb.keyframe_insert("rotation_euler", frame=f)

def simulate(arm, frames, fps, preset, gravity=1.0, damping=0.08):
    """preset: [(stiffness, distance)] for penis_02, penis_03, penis_04, tip."""
    sc = bpy.context.scene
    rest = {n: arm.data.bones[n].matrix_local.copy() for n in CHAIN}
    seg = rest["penis_04"].translation - rest["penis_03"].translation
    def targets():
        mw = arm.matrix_world
        heads = [mw @ arm.pose.bones[n].head for n in CHAIN]
        tip = mw @ (arm.pose.bones["penis_04"].matrix @ (rest["penis_04"].inverted() @ (rest["penis_04"].translation + seg)))
        return heads + [tip]
    for n in CHAIN:
        arm.pose.bones[n].matrix_basis = Matrix.Identity(4)
    sc.frame_set(0); x = targets(); xp = [v.copy() for v in x]
    L = [(x[i + 1] - x[i]).length for i in range(4)]
    g = Vector((0, 0, -9.81 * gravity)); dt = 1.0 / fps
    out = []
    for f in range(frames + 1):
        sc.frame_set(f)
        for n in CHAIN:
            arm.pose.bones[n].matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        tg = targets()
        x[0] = tg[0]
        for i in range(1, 5):
            s, d = preset[i - 1]
            v = (x[i] - xp[i]) * (1 - damping)
            xp[i] = x[i].copy()
            x[i] = x[i] + v + g * dt * dt
            x[i] = x[i] + (tg[i] - x[i]) * s
            off = x[i] - tg[i]
            if off.length > d:
                x[i] = tg[i] + off.normalized() * d
        for i in range(1, 5):   # links, base to tip
            e = x[i] - x[i - 1]
            x[i] = x[i - 1] + e.normalized() * L[i - 1]
        out.append([v.copy() for v in x])
    return out

def bake(arm, sim):
    """Aim each chain bone from its rest direction at the simulated next node."""
    sc = bpy.context.scene; inv = arm.matrix_world.inverted()
    for f, x in enumerate(sim):
        sc.frame_set(f)
        for i, n in enumerate(CHAIN):
            pb = arm.pose.bones[n]; pb.rotation_mode = "QUATERNION"
            pb.matrix_basis = Matrix.Identity(4); bpy.context.view_layer.update()
            m = pb.matrix.copy()
            a = (inv @ x[i + 1]) - m.translation
            cur_tip = (arm.pose.bones[CHAIN[i + 1]].head if i < 3 else None)
            b = (cur_tip - m.translation) if cur_tip is not None else \
                (m @ (pb.bone.matrix_local.inverted() @ (pb.bone.matrix_local.translation +
                     (arm.data.bones["penis_04"].matrix_local.translation - arm.data.bones["penis_03"].matrix_local.translation)))) - m.translation
            q = b.rotation_difference(a)
            new = Matrix.Translation(m.translation) @ q.to_matrix().to_4x4() @ Matrix.Translation(-m.translation) @ m
            pb.matrix = new; bpy.context.view_layer.update()
            pb.keyframe_insert("rotation_quaternion", frame=f)
