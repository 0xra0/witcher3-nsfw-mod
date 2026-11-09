"""Headless: her mouth onto Geralt's shaft (oral), solved per frame after the retarget.

  blender -b in.blend --python mouth_her.py -- mouth.json out.blend

mouth.json:
  {"depth": [[0.13, 0.16], [0.11, 0.16], [0.09, 0.15], [0.09, 0.15]],
                        # per stage [deep, shallow]: lip point along the shaft from penis_01, metres
   "stage_len": 120,    # frames per stage in the plan's timeline (last stage takes the rest)
   "aim_max_deg": 35,   # penis_01 may turn this far toward her mouth
   "chain": {"torso2": 0.25, "torso3": 0.35, "neck": 0.6},   # CCD share per step
   "iters": 12, "smooth": 3,
   "ease_jumps": 8,                      # cross-fade the source clip over +-N frames at each stage seam
   "rise_max": 0.3, "rise_smooth": 8,    # kneel-up limit and its +-frames smoothing
   "slide_smooth": 12, "body_step": 4, "face_share": 0.8}

The SLAL clip was made for a Skyrim penis that bends toward her mouth; Geralt's keeps the
c41 erection, so after the retarget her mouth is 12-15 cm off the shaft. Per frame:
1. penis_01 turns toward her mouth (clamped to aim_max_deg about its own head);
2. the lip point (her upper/lower lip midpoint) goes to base + axis * depth, depth = her SLAL
   head bob along the shaft rescaled per stage onto that stage's [deep, shallow] range;
3. CCD over the spine/neck chain moves the lips, the head turns her face down the shaft
   (face forward = -axis), alternating until both hold.
Run before hands_her.py: the hand grip reads the shaft after it has been aimed."""
import json, math, os, sys
import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.geometry import intersect_point_line
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nla_keys import _fcurves, frame_range, smooth_list, track, write

CFG, OUT = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(CFG))
P = bpy.data.objects["prostitute:CMovingPhysicalAgentComponent2_ARM"]
G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]
M = bpy.data.objects["prostitute:CMimicComponent12_ARM"]   # face bones; its head copies P's head
sc = bpy.context.scene
lo, hi = frame_range(P)
frames = list(range(lo, hi + 1))
CHAIN = cfg.get("chain", {"torso2": 0.25, "torso3": 0.35, "neck": 0.6})
ITERS, AIM_MAX = cfg.get("iters", 12), math.radians(cfg.get("aim_max_deg", 35))
STAGE = cfg.get("stage_len", 120)


def W(A, n, tail=False):
    pb = A.pose.bones[n]
    return A.matrix_world @ (pb.tail if tail else pb.head)


def lips():
    return (W(M, "upper_lip") + W(M, "lowwer_lip")) / 2


def face_fwd():
    """Out of the face: (eye line) x (chin -> forehead), signed to point away from the skull."""
    right = W(M, "right_eye") - W(M, "left_eye")
    up = (W(M, "left_forehead") + W(M, "right_forehead")) / 2 - W(M, "chin")
    f = right.cross(up).normalized()
    return f if f.dot(W(M, "nose") - W(P, "head")) > 0 else -f


def shaft():
    b = W(G, "penis_01")
    return b, (W(G, "penis_04", True) - b).normalized()


def rotate_about(A, pb, R, pivot_world):
    """Pre-multiply the bone's pose by world rotation R about pivot (see hands_her.py)."""
    A3 = A.matrix_world.to_3x3().normalized()
    Ra = (A3.inverted() @ R.normalized() @ A3).to_4x4()
    p = A.matrix_world.inverted() @ pivot_world
    pb.matrix = Matrix.Translation(p) @ Ra @ Matrix.Translation(-p) @ pb.matrix
    pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()


def turn(a, b, share=1.0, limit=None):
    """World rotation taking direction a toward b, scaled by share and clamped to limit rad."""
    q = a.rotation_difference(b)
    ang = q.angle * share
    if limit is not None:
        ang = min(ang, limit)
    return Matrix.Rotation(ang, 3, q.axis) if ang > 1e-6 else Matrix.Identity(3)


def stage_of(g):
    return min((g - lo) // STAGE, len(cfg["depth"]) - 1)


def ease(x):
    return x * x * (3 - 2 * x)


# Pass 0: the SLAL stages start from different poses (her pelvis turns 9-15 deg in one frame
# at each seam). Cross-fade the source clip, every bone of both actors, over +-N frames there
# so the solver starts from a continuous body. Easing only the solved keys afterwards is worse:
# the bones it does not key (pelvis rotation, torso) still jump.
N = cfg.get("ease_jumps", 0)
SEAMS = [lo + s * STAGE for s in range(1, len(cfg["depth"]))] if N else []
for A in (P, G):
    keyed = {fc.data_path for fc in _fcurves(track(A).strips[0].action)}
    for j in SEAMS:
        ends = []
        for g in (j - N, j + N):
            sc.frame_set(g)
            ends.append({pb.name: (pb.location.copy(), pb.rotation_quaternion.copy()) for pb in A.pose.bones})
        for n, (l0, q0) in ends[0].items():
            l1, q1 = ends[1][n]
            if q0.dot(q1) < 0:
                q1.negate()
            span = range(j - N + 1, j + N)
            if 'pose.bones["%s"].location' % n in keyed:
                write(A, n, "location", {g: tuple(l0.lerp(l1, ease((g - j + N) / (2 * N)))) for g in span})
            if 'pose.bones["%s"].rotation_quaternion' % n in keyed:
                write(A, n, "rotation_quaternion", {g: tuple(q0.slerp(q1, ease((g - j + N) / (2 * N)))) for g in span})
for j in SEAMS:
    print("MOUTH eased source clip over f%d-%d" % (j - N, j + N))

# Pass 1: her SLAL head bob along the (unaimed) shaft -> per-stage depth.
bob = []
for g in frames:
    sc.frame_set(g)
    b, ax = shaft()
    bob.append((lips() - b).dot(ax))
segs = [sorted(bob[s * STAGE:(s + 1) * STAGE] if s < len(cfg["depth"]) - 1 else bob[s * STAGE:])
        for s in range(len(cfg["depth"]))]


def depth_in(s, i):
    """Frame i's bob mapped onto stage s's [deep, shallow] range."""
    seg = segs[s]
    p5, p95 = seg[int(0.05 * (len(seg) - 1))], seg[int(0.95 * (len(seg) - 1))]
    k = 0.5 if p95 - p5 < 1e-4 else min(1.0, max(0.0, (bob[i] - p5) / (p95 - p5)))
    deep, shallow = cfg["depth"][s]
    return deep + k * (shallow - deep)   # head further out along the shaft = shallower


depth = []
for i, g in enumerate(frames):
    d = depth_in(stage_of(g), i)
    for j in SEAMS:   # near a seam, blend the two stages' mappings instead of switching
        if abs(g - j) < N:
            x = ease((g - j + N) / (2 * N))
            d = depth_in(stage_of(j) - 1, i) * (1 - x) + depth_in(stage_of(j), i) * x
    depth.append(d)


def aim_penis():
    """penis_01 toward her lips, clamped; returns (base, axis, angle deg)."""
    b, ax = shaft()
    R = turn(ax, (lips() - b).normalized(), limit=AIM_MAX)
    rotate_about(G, G.pose.bones["penis_01"], R, b)
    b, ax = shaft()
    return b, ax, math.degrees(R.to_quaternion().angle)


def rise(dz):
    """Lift her pelvis by dz with the knees planted: the hips swing up round the knees
    (kneeling up from her heels), shins and feet keep their world pose."""
    K = {s: W(P, s + "_shin") for s in "lr"}
    H = {s: W(P, s + "_thigh") for s in "lr"}
    L = {s: (H[s] - K[s]).length for s in "lr"}
    shin = {s: P.pose.bones[s + "_shin"].matrix.copy() for s in "lr"}
    hip, knee = (H["l"] + H["r"]) / 2, (K["l"] + K["r"]) / 2
    back = Vector((hip.x - knee.x, hip.y - knee.y, 0))
    back = back.normalized() if back.length > 0.02 else -Vector((face_fwd().x, face_fwd().y, 0)).normalized()

    def miss(f):
        d = Vector((0, 0, dz)) + back * f
        return sum((H[s] + d - K[s]).length - L[s] for s in "lr") / 2
    a, b = -0.35, 0.35            # hips move toward (f < 0) or away from the knees
    if miss(a) * miss(b) > 0:     # out of reach: keep the leg pose
        return False
    for _ in range(30):
        m = (a + b) / 2
        if miss(a) * miss(m) <= 0:
            b = m
        else:
            a = m
    d = Vector((0, 0, dz)) + back * (a + b) / 2
    pel = P.pose.bones["pelvis"]
    pel.matrix = Matrix.Translation(P.matrix_world.to_3x3().inverted() @ d) @ pel.matrix
    bpy.context.view_layer.update()
    for s in "lr":
        piv = W(P, s + "_thigh")
        rotate_about(P, P.pose.bones[s + "_thigh"], turn(W(P, s + "_shin") - piv, K[s] - piv), piv)
        P.pose.bones[s + "_shin"].matrix = shin[s]
        bpy.context.view_layer.update()
    return True


def shift(d):
    """Slide her whole body (Root) by world vector d."""
    rt = P.pose.bones["Root"]
    rt.matrix = Matrix.Translation(P.matrix_world.to_3x3().inverted() @ d) @ rt.matrix
    bpy.context.view_layer.update()


def solve_chain(T, want, iters):
    """Orientation and position are split, or they undo each other (a head turn about its
    pivot swings the lips ~10 cm): the head takes the face direction in place, then the
    chain carries the head pivot to where that puts the lips on T."""
    for _ in range(iters):
        rotate_about(P, P.pose.bones["head"], turn(face_fwd(), want), W(P, "head"))
        hp = W(P, "head") + (T - lips())
        for n, share in CHAIN.items():
            piv = W(P, n)
            rotate_about(P, P.pose.bones[n], turn(W(P, "head") - piv, hp - piv, share), piv)
        if (lips() - T).length < 0.003 and face_fwd().angle(want) < 0.03:
            break
    rotate_about(P, P.pose.bones["head"], turn(face_fwd(), want), W(P, "head"))


def targets(i):
    """Aim the shaft at her lips; return (axis, lip target, wanted face direction)."""
    b, ax, a = aim_penis()
    return ax, b + ax * depth[i], turn(face_fwd(), -ax, cfg.get("face_share", 0.8)) @ face_fwd(), a


# Pass 2: how far her body must move. Aim, body and chain depend on each other, so on every
# body_step-th frame they are solved together: the chain first, what it cannot reach goes to
# the body (vertical = kneel up, knees planted; horizontal = slide), repeat. The body path is
# then interpolated and smoothed, and pass 3 solves only the chain on top of it.
RISE, STEP = cfg.get("rise_max", 0.3), cfg.get("body_step", 4)
samp = frames[::STEP] + ([hi] if (hi - lo) % STEP else [])
bz, bxy = [], []
for g in samp:
    i = g - lo
    sc.frame_set(g)
    ax, T, want, _ = targets(i)
    tz, txy = 0.0, Vector((0, 0, 0))
    for _ in range(5):
        solve_chain(T, want, ITERS // 2)
        r = T - lips()
        if r.length < 0.005:
            break
        z = min(RISE - tz, max(-0.05 - tz, r.z))
        if rise(z):
            tz += z
        shift(Vector((r.x, r.y, 0)))
        txy += Vector((r.x, r.y, 0))
    bz.append(tz)
    bxy.append(txy)


def spread(vals, half):
    """Samples -> every frame (linear), then a moving average."""
    out = []
    for g in frames:
        k = min((g - lo) // STEP, len(samp) - 2)
        t = (g - samp[k]) / (samp[k + 1] - samp[k])
        out.append(vals[k] * (1 - t) + vals[k + 1] * t)
    return smooth_list(out, half)


dz = spread(bz, cfg.get("rise_smooth", 8))
dxy = spread(bxy, cfg.get("slide_smooth", 12))
dx, dy = [v.x for v in dxy], [v.y for v in dxy]
print("MOUTH body: rise %.3f..%.3f m, slide %.3f..%.3f m" % (min(dz), max(dz), min(v.length for v in dxy),
      max(v.length for v in dxy)))

# Pass 3: per frame body, aim, CCD, face turn; key the local transforms.
LOCS = ["Root", "pelvis"]
ROTS = ["penis_01", "l_thigh", "r_thigh", "l_shin", "r_shin"] + list(CHAIN) + ["head"]
keys = {n: [] for n in LOCS + ROTS}
errs, aims, faces, nofit = [], [], [], 0
TEST = cfg.get("test_frames")   # debugging: solve and report only these frames, save nothing
for i, g in enumerate(frames):
    if TEST and g not in TEST:
        continue
    sc.frame_set(g)
    ax, T, want, a = targets(i)          # aimed before the body moves, as in pass 2
    aims.append(a)
    shift(Vector((dx[i], dy[i], 0)))
    nofit += not rise(dz[i])
    solve_chain(T, want, ITERS)
    errs.append((lips() - T).length)
    if TEST:
        print("MOUTH test f=%3d lip err %.3f face %.0f deg" % (g, errs[-1], math.degrees(face_fwd().angle(-ax))))
        continue
    faces.append(math.degrees(face_fwd().angle(-ax)))
    for n in LOCS:
        keys[n].append(P.pose.bones[n].location.copy())
    for n in ROTS:
        keys[n].append((G if n == "penis_01" else P).pose.bones[n].rotation_quaternion.copy())

if TEST:
    sys.exit(0)
H = cfg.get("smooth", 3)
for n in LOCS:
    write(P, n, "location", {g: tuple(v) for g, v in zip(frames, smooth_list(keys[n], H))})
for n in ROTS:
    qs = keys[n]
    for j in range(1, len(qs)):
        if qs[j].dot(qs[j - 1]) < 0:
            qs[j].negate()
    sm = smooth_list([Vector(q) for q in qs], H)   # Quaternion has no "/"
    # Back to Quaternion before normalizing: a 4D Vector.normalized() scales only xyz (Blender 5.2).
    write(G if n == "penis_01" else P, n, "rotation_quaternion",
          {g: tuple(Quaternion(v).normalized()) for g, v in zip(frames, sm)})
print("MOUTH rise out of leg reach on %d frames" % nofit)
print("MOUTH lip error before smoothing: max %.3f mean %.3f m" % (max(errs), sum(errs) / len(errs)))
print("MOUTH face vs shaft: max %.0f mean %.0f deg; penis aim max %.0f deg" %
      (max(faces), sum(faces) / len(faces), max(aims)))
for g in frames[::30]:
    sc.frame_set(g)
    b, ax = shaft()
    q, t = intersect_point_line(lips(), b, b + ax)
    print("MOUTH f=%3d off_axis %.3f along %.3f (target %.3f)" % (g, (lips() - q).length, t, depth[g - lo]))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
