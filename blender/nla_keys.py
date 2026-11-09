"""Write per-frame pose keys back into the exported cutscene's NLA strip actions.

The imported cutscene has one action per shot (6 strips per actor, keyed every frame,
neighbouring strips share their boundary frame), and export_blend.py reads those fcurves,
so a pass that changes the pose must rewrite the keys in every strip."""


def track(arm):
    return next(t for t in arm.animation_data.nla_tracks if t.name.startswith("cutscene_anim_file"))


def frame_range(arm):
    s = track(arm).strips
    return min(int(round(x.frame_start)) for x in s), max(int(round(x.frame_end)) for x in s)


def _fcurves(act):
    cb = act.layers[0].strips[0].channelbags[0] if hasattr(act, "layers") and act.layers else None
    return cb.fcurves if cb else act.fcurves


def write(arm, bone, prop, values):
    """values: {frame: sequence}; prop "location" or "rotation_quaternion"."""
    lo, hi = frame_range(arm)
    path = 'pose.bones["%s"].%s' % (bone, prop)
    for strip in track(arm).strips:
        chans = sorted((fc for fc in _fcurves(strip.action) if fc.data_path == path),
                       key=lambda fc: fc.array_index)
        assert chans, (strip.name, path)
        g0 = int(round(strip.frame_start))
        for j in range(len(chans[0].keyframe_points)):
            v = values.get(min(hi, g0 + j))
            if v is None:
                continue
            for i, fc in enumerate(chans):
                fc.keyframe_points[j].co[1] = v[i]
        for fc in chans:
            fc.update()


def local_of(arm, pb, pose_matrix):
    """Armature-space pose matrix -> the bone's local (keyed) matrix, parents as evaluated now."""
    return arm.convert_space(pose_bone=pb, matrix=pose_matrix, from_space="POSE", to_space="LOCAL")


def smooth_list(xs, half):
    n = len(xs)
    return [sum(xs[max(0, i - half):min(n, i + half + 1)], xs[0] * 0) /
            (min(n, i + half + 1) - max(0, i - half)) for i in range(n)]
