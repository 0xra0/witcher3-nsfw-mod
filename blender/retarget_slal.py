"""Headless: retarget a two-actor SLAL (Skyrim) scene onto the imported sex_do_component rigs.

  blender -b sex_do_component_import.blend --python retarget_slal.py -- plan.json out.blend

plan.json:
  {"skeleton": {"geralt": ".../skeleton.xml", "prostitute": ".../skeleton_female.xml"},
   "anims":    {"geralt": [stage json, ...], "prostitute": [...]},   # hkx_tagfile.py output
   "timeline": [[stage_index, first_frame, frame_count], ...],        # fills frames 0..N
   "offset": [x, y, z],                                              # metres, both actors
   "fit": {"penis_base": [x,y,z], "penis_tip": [x,y,z],             # Geralt rest space
           "body_mesh": "twals_03_wa__body", "vulva_verts": [i, j],  # her mesh, crotch seam
           "window_s": 1.2, "step": 2}}                              # optional, see fit_shift

Skyrim and these Witcher rigs share axes (Z up, facing +Y, left = -X), so only units
change (1 Skyrim unit = 1/70 m). Each mapped Witcher bone gets the Skyrim bone's world
rotation times a fixed offset taken from a "matched rest": the Witcher rest bone
re-aimed along the Skyrim rest bone. That keeps the A-pose/T-pose difference out of the
animation. Only the pelvis takes translation; every other bone keeps Witcher lengths.
SLAL actors share one origin, so both rigs stay at the cutscene origin.
"""
import bisect
import itertools
import json
import os
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skyrim_skeleton import load_skeleton  # noqa: E402

UNIT = 1.0 / 70.0
RIGS = {"geralt": "geralt:CMovingPhysicalAgentComponent25_ARM",
        "prostitute": "prostitute:CMovingPhysicalAgentComponent2_ARM"}

# Witcher bone -> (Skyrim bone, Skyrim aim child, Witcher aim child). An aim of None
# keeps the rest orientations as they are (upright spine/pelvis/head in both rigs).
SIDE = {
    "{s}_shoulder": ("NPC {S} Clavicle [{S}Clv]", "NPC {S} UpperArm [{S}Uar]", "{s}_bicep"),
    "{s}_bicep": ("NPC {S} UpperArm [{S}Uar]", "NPC {S} Forearm [{S}Lar]", "{s}_forearm"),
    "{s}_forearm": ("NPC {S} Forearm [{S}Lar]", "NPC {S} Hand [{S}Hnd]", "{s}_hand"),
    "{s}_hand": ("NPC {S} Hand [{S}Hnd]", "NPC {S} Finger20 [{S}F20]", "{s}_middle1"),
    "{s}_thigh": ("NPC {S} Thigh [{S}Thg]", "NPC {S} Calf [{S}Clf]", "{s}_shin"),
    "{s}_shin": ("NPC {S} Calf [{S}Clf]", "NPC {S} Foot [{S}ft ]", "{s}_foot"),
    "{s}_foot": ("NPC {S} Foot [{S}ft ]", "NPC {S} Toe0 [{S}Toe]", "{s}_toe"),
    "{s}_toe": ("NPC {S} Toe0 [{S}Toe]", None, None),
}
for finger, sk in (("thumb", 0), ("index", 1), ("middle", 2), ("ring", 3), ("pinky", 4)):
    for j in range(3):
        aim = ("NPC {S} Finger%d%d [{S}F%d%d]" % (sk, j + 1, sk, j + 1), "{s}_%s%d" % (finger, j + 2)) if j < 2 else (None, None)
        SIDE["{s}_%s%d" % (finger, j + 1)] = ("NPC {S} Finger%d%d [{S}F%d%d]" % (sk, j, sk, j),) + aim
BONE_MAP = {
    "pelvis": ("NPC Pelvis [Pelv]", None, None),
    "torso": ("NPC Spine [Spn0]", "NPC Spine1 [Spn1]", "torso2"),
    "torso2": ("NPC Spine1 [Spn1]", "NPC Spine2 [Spn2]", "torso3"),
    "torso3": ("NPC Spine2 [Spn2]", "NPC Neck [Neck]", "neck"),
    "neck": ("NPC Neck [Neck]", "NPC Head [Head]", "head"),
    "head": ("NPC Head [Head]", None, None),
}
for s, S in (("l", "L"), ("r", "R")):
    for w, spec in SIDE.items():
        BONE_MAP[w.format(s=s)] = tuple(None if x is None else x.format(s=s, S=S) for x in spec)


def trs(t, q_xyzw, scale=UNIT):
    m = Quaternion((q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2])).to_matrix().to_4x4()
    m.translation = Vector(t) * scale
    return m


def skyrim_world(names, parents, locals_):
    out = []
    for i, m in enumerate(locals_):
        out.append(m if parents[i] < 0 else out[parents[i]] @ m)
    return {n: out[i] for i, n in enumerate(names)}


def rot3(m):
    return m.to_3x3().normalized()


def matched_offsets(arm, sk_rest):
    """Witcher bone -> 3x3 offset so that W_world_rot = S_world_rot @ offset."""
    offs = {}
    for w, (s, s_aim, w_aim) in BONE_MAP.items():
        b = arm.data.bones.get(w)
        if b is None or s not in sk_rest:
            continue
        rw = rot3(b.matrix_local)
        if s_aim and w_aim and s_aim in sk_rest and w_aim in arm.data.bones:
            dw = arm.data.bones[w_aim].head_local - b.head_local
            ds = sk_rest[s_aim].translation - sk_rest[s].translation
            if dw.length > 1e-6 and ds.length > 1e-6:
                rw = dw.rotation_difference(ds).to_matrix() @ rw
        offs[w] = rot3(sk_rest[s]).inverted() @ rw
    return offs


def channelbag(action):
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                return cb
    raise RuntimeError("action %s has no channelbag" % action.name)


def compute_actor(arm, skeleton_path, stage_paths, timeline, offset, pelvis_shift=None):
    """Per global frame: (bone -> basis Matrix, bone -> armature-space skin Matrix).
    pelvis_shift: optional per-frame armature-space Vector added to the pelvis."""
    names, parents, ref = load_skeleton(skeleton_path)
    ref_local = [trs(t, q) for t, q in ref]
    sk_rest = skyrim_world(names, parents, ref_local)
    offs = matched_offsets(arm, sk_rest)
    stages = [json.load(open(p)) for p in stage_paths]
    shift = Matrix.Translation(Vector(offset))

    bones = sorted(arm.data.bones, key=lambda b: len(b.parent_recursive))
    rest = {b.name: b.matrix_local.copy() for b in bones}
    frames, skins = [], []
    for stage_i, first, count in timeline:
        st = stages[stage_i]
        for f in range(first, first + count):
            f = min(f, st["num_frames"] - 1)
            loc = list(ref_local)
            for i, n in enumerate(names):
                tr = st["tracks"].get(n)
                if tr:
                    loc[i] = trs(tr["t"][f], tr["r"][f])
            sw = skyrim_world(names, parents, loc)
            pose, basis = {}, {}
            for b in bones:
                p = b.parent
                chain = (pose[p.name] @ rest[p.name].inverted() @ rest[b.name]) if p else rest[b.name]
                if b.name in offs:
                    s = BONE_MAP[b.name][0]
                    m = (rot3(sw[s]) @ offs[b.name]).to_4x4()
                    if b.name == "pelvis":
                        m.translation = (shift @ sw[s]).translation
                        if pelvis_shift:
                            m.translation += pelvis_shift[len(frames)]
                    else:
                        m.translation = chain.translation
                else:
                    m = chain
                pose[b.name] = m
                basis[b.name] = chain.inverted() @ m
            frames.append(basis)
            skins.append({n: pose[n] @ rest[n].inverted() for n in pose})
    return frames, skins, len(offs)


def fit_shift(g_arm, g_skins, p_body, cfg, fps):
    """Per-frame world shift for the prostitute that buries Geralt's penis in her mesh.

    The GeraltX penis is a rigid shape skinned only to `pelvis`; it has no genital bones
    like Skyrim's SOS chain, which SLAL keys to bend the penis into the partner. Her
    crotch is skinned ~95% to the thighs, so with raised legs it is not where any rest
    anatomy predicts. So this measures the visible result instead: every `step` frames,
    grid-search a translation of her evaluated mesh so the shaft samples are inside it,
    the base is outside and her crotch (mean of `vulva_verts`) sits on the shaft near
    its base.
    Many shifts tie on the integer inside count, so each frame searches around the
    previous answer and pays for jumping away from it; otherwise neighbours disagree.
    Smoothing over about one stroke keeps Geralt's thrust as motion."""
    pb, pt = Vector(cfg["penis_base"]), Vector(cfg["penis_tip"])
    ks = cfg.get("shaft_samples", [0.35, 0.5, 0.65, 0.8, 0.95])
    scene, step = bpy.context.scene, cfg.get("step", 1)

    def inside(bvh, q):
        loc, n, _, _ = bvh.find_nearest(q)
        return loc is not None and (q - loc).dot(n) < 0

    def score(bvh, vul, b, t, s, prev):
        v = vul + s
        axis, length = (t - b).normalized(), (t - b).length
        along = (v - b).dot(axis) / length
        perp = ((v - b) - axis * along * length).length
        # Inside counts only near her crotch, or the shaft gets buried in a raised thigh.
        n_in = sum(inside(bvh, q - s) and (q - v).length < 0.15
                   for q in (b + (t - b) * k for k in ks))
        base_out = 1 if not inside(bvh, b - s) else -2
        entry = 10 * perp + 5 * length * (max(0.0, 0.1 - along) + max(0.0, along - 0.45))
        return n_in + base_out - entry - s.length - 8 * (s - prev).length

    keys, fitted, prev = [], [], Vector()
    for f in list(range(0, len(g_skins), step)) + [len(g_skins) - 1]:
        scene.frame_set(scene.frame_start + f)
        ev = p_body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        me.transform(ev.matrix_world)
        bvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
        vul = sum((me.vertices[i].co for i in cfg["vulva_verts"]), Vector()) / len(cfg["vulva_verts"])
        ev.to_mesh_clear()
        gm = g_arm.matrix_world @ g_skins[f]["pelvis"]
        b, t = gm @ pb, gm @ pt
        best = (score(bvh, vul, b, t, prev, prev), prev)
        for size, reach in ((0.04, 3), (0.015, 3), (0.005, 3)):
            centre = best[1].copy()
            for i, j, k in itertools.product(range(-reach, reach + 1), repeat=3):
                s = centre + Vector((i, j, k)) * size
                sc = score(bvh, vul, b, t, s, prev)
                if sc > best[0]:
                    best = (sc, s)
        keys.append(f)
        fitted.append(best[1])
        prev = best[1]
    dense = []
    for f in range(len(g_skins)):
        i = min(bisect.bisect_right(keys, f), len(keys) - 1)
        u = (f - keys[i - 1]) / max(1, keys[i] - keys[i - 1])
        dense.append(fitted[i - 1].lerp(fitted[i], u))
    half = int(cfg.get("window_s", 1.2) * fps / 2)
    return [sum(dense[max(0, i - half):i + half + 1], Vector()) / len(dense[max(0, i - half):i + half + 1])
            for i in range(len(dense))]


def write_keys(arm, frames):
    """Write keys into each NLA strip's action at its local frames."""
    bones = sorted(arm.data.bones, key=lambda b: len(b.parent_recursive))
    track = next(t for t in arm.animation_data.nla_tracks if t.name.startswith("cutscene_anim_file"))
    written = 0
    for strip in track.strips:
        cb = channelbag(strip.action)
        for fc in [fc for fc in cb.fcurves if fc.data_path.startswith("pose.bones")]:
            cb.fcurves.remove(fc)
        g0, g1 = int(round(strip.frame_start)), int(round(strip.frame_end))
        span = [min(g, len(frames) - 1) for g in range(g0, g1 + 1)]
        for b in bones:
            pb = arm.pose.bones[b.name]
            pb.rotation_mode = "QUATERNION"
            locs, quats, prev = [], [], None
            for g in span:
                m = frames[g][b.name]
                q = m.to_quaternion()
                if prev is not None and q.dot(prev) < 0:
                    q.negate()
                prev = q
                locs.append(m.translation)
                quats.append(q)
            path = 'pose.bones["%s"]' % b.name
            for prop, vals, n in (("location", locs, 3), ("rotation_quaternion", quats, 4)):
                for i in range(n):
                    fc = cb.fcurves.new(path + "." + prop, index=i, group_name=b.name)
                    fc.keyframe_points.add(len(span))
                    co = []
                    for k, v in enumerate(vals):
                        co += [float(k), float(v[i])]
                    fc.keyframe_points.foreach_set("co", co)
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"
                    fc.update()
        written += len(span)
    return written


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    plan = json.load(open(argv[0]))
    args = {a: (bpy.data.objects[r], plan["skeleton"][a], plan["anims"][a], plan["timeline"],
                plan.get("offset", [0, 0, 0])) for a, r in RIGS.items()}
    result = {a: compute_actor(*args[a]) for a in RIGS}
    fit = plan.get("fit")
    if fit:
        # Her body mesh follows the rig only through keys, so key her unshifted pose first.
        write_keys(args["prostitute"][0], result["prostitute"][0])
        scene = bpy.context.scene
        p_arm = args["prostitute"][0]
        p_body = next(o for o in bpy.data.objects if o.type == "MESH" and fit["body_mesh"] in o.name)
        world = fit_shift(args["geralt"][0], result["geralt"][1], p_body, fit,
                          scene.render.fps / scene.render.fps_base)
        to_arm = p_arm.matrix_world.to_3x3().inverted()
        result["prostitute"] = compute_actor(*args["prostitute"], pelvis_shift=[to_arm @ w for w in world])
        print("FIT shift_len min %.3f max %.3f  z min %.3f max %.3f" % (
            min(w.length for w in world), max(w.length for w in world),
            min(w.z for w in world), max(w.z for w in world)))
    for a in RIGS:
        frames, _, mapped = result[a]
        print("RETARGET", a, dict(mapped=mapped, frames=len(frames), keyed=write_keys(args[a][0], frames)))
    bpy.ops.wm.save_as_mainfile(filepath=argv[1])


if __name__ == "__main__":
    main()
