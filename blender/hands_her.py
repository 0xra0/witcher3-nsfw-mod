"""Headless: her hands hold her legs (back of the thigh near the knee), solved by IK.

  blender -b in.blend --python hands_her.py -- hands.json out.blend

hands.json:
  {"body_mesh": "twals_03_wa__body",
   "t": 0.75,            # grip point along the thigh, hip (0) -> knee (1)
   "around_deg": 50,     # from the back of the thigh (0) toward its outer side (90)
   "curl_deg": [25, 25, 20],   # per finger joint, wraps the fingers round the thigh
   "pole": [1.0, -0.6],  # elbow hint: her outward side, world down (toward the bed)
   "smooth": 4}          # +-frames on the grip targets

The SLAL arms were made for Skyrim's proportions, so after the retarget her hands ended
up inside her thighs (stage 1) or at her neck (stage 2). This puts each palm on her
evaluated skin (raycast from the thigh axis), fingers wrapping round the leg, and solves
shoulder -> elbow -> wrist analytically. The hand's twist about the forearm is spread
over the forearm roll bones (1/3, 2/3, 1) so the wrist skin does not wring.
Run last, after every pass that moves her legs (shift, stroke).

"grip": "shaft" puts the hand round Geralt's penis instead (handjob):
  {"grip": "shaft", "sides": "r",
   "stroke": [0.045, 0.095],   # palm centre along the shaft from penis_01, metres
   "shaft_mesh": "game_l_01_mg__body", "radius": 0.019,   # surface by raycast, else radius
   "curl_deg": [55, 60, 45], "thumb_deg": [20, 35, 30]}
The palm keeps the side of the shaft the SLAL hand was on, and the SLAL stroke (the palm
projected on the shaft over the whole clip) is rescaled onto "stroke", so the rhythm stays
while the hand stays on our shorter shaft. The thumb points toward the tip.

"grip": "balls" cups the testicles from below (palm up, fingers back between his legs):
  {"grip": "balls", "sides": "l", "shaft_mesh": "game_l_01_mg__body",
   "balls": [-0.024, 0.0, -0.055],   # centre from penis_01: forward, left, up (metres)
   "curl_deg": [25, 30, 20], "thumb_deg": [10, 15, 10]}
Forward is the shaft direction made horizontal, up is world Z (he stands). The palm goes
on the underside found by a raycast up from below the centre. Run after the shaft pass."""
import json, math, os, sys
import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nla_keys import frame_range, local_of, smooth_list, write

CFG, OUT = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(CFG))
P = bpy.data.objects["prostitute:CMovingPhysicalAgentComponent2_ARM"]
# "pose": grip.json from work/scratch/hj9/extract.py (a vanilla woman_work clip): fixed finger
# rotations per hand, plus the held handle's axis/centre in the hand's frame. The handle goes
# onto the shaft axis; curl_deg/thumb_deg/wrap_gap/approach are then unused.
POSE = json.load(open(cfg["pose"])) if cfg.get("pose") else None
SHAFT, BALLS = cfg.get("grip") == "shaft", cfg.get("grip") == "balls"
body = bpy.data.objects.get(cfg["shaft_mesh"]) if SHAFT or BALLS else \
    next(o for o in bpy.data.objects if o.type == "MESH" and cfg["body_mesh"] in o.name)
SIDES = cfg.get("sides", "lr")
sc = bpy.context.scene
lo, hi = frame_range(P)
frames = list(range(lo, hi + 1))
pbs, bones = P.pose.bones, P.data.bones
AW = P.matrix_world
FINGERS = ("index", "middle", "ring", "pinky")


def head(n):
    return AW @ pbs[n].head


def rot_world(n):
    return (AW @ pbs[n].matrix).to_3x3().normalized()


def rest_rot(n):
    return bones[n].matrix_local.to_3x3().normalized()


def side_vec(s, rest_vec, bone, A=None):
    """A rest-space direction carried along by the bone's current rotation (of armature A, default hers)."""
    if A is None:
        return (rot_world(bone) @ rest_rot(bone).inverted() @ Vector(rest_vec)).normalized()
    rw = (A.matrix_world @ A.pose.bones[bone].matrix).to_3x3().normalized()
    return (rw @ A.data.bones[bone].matrix_local.to_3x3().normalized().inverted() @ Vector(rest_vec)).normalized()


# The palm side in the hand's own frame: the mean way the fingertips curl over the clip.
hand_axes, thumb_sign = {}, {}
for s in SIDES:
    fwd, curl = Vector(), Vector()
    for g in frames[::10]:
        sc.frame_set(g)
        inv = rot_world(s + "_hand").inverted()
        f = (head(s + "_middle1") - head(s + "_hand")).normalized()
        c = head(s + "_middle3") - head(s + "_middle1")
        fwd += inv @ f
        curl += inv @ (c - f * c.dot(f))
    fwd.normalize()
    curl = (curl - fwd * curl.dot(fwd)).normalized()
    hand_axes[s] = (fwd, curl)
    # Which way the thumb sticks out along fwd x curl (opposite for the two hands).
    th = rot_world(s + "_hand").inverted() @ (head(s + "_thumb1") - head(s + "_hand"))
    thumb_sign[s] = 1.0 if th.dot(fwd.cross(curl)) > 0 else -1.0
    print("HANDS %s palm-side (hand local) %s" % (s, tuple(round(x, 2) for x in curl)))


def frame_of(f, n):
    n = (n - f * n.dot(f)).normalized()
    return Matrix((f, n, f.cross(n))).transposed()


def pose_frame(g, q, axis, shoulder):
    """World rotation of the hand that lays the grip's handle (pinky -> index) along the shaft,
    index toward the tip, rolled about the shaft so the forearm (hand -Y) points at her shoulder."""
    a, c = Vector(g["axis"]), Vector(g["centre"])
    base = frame_of(axis, axis.orthogonal()) @ frame_of(a, a.orthogonal()).inverted()
    best = None
    for k in range(180):
        H = Matrix.Rotation(math.radians(2 * k), 3, axis) @ base
        score = (H @ Vector((0, -1, 0))).dot((shoulder - (q - H @ c)).normalized())
        if best is None or score > best[0]:
            best = (score, H)
    return best[1]


# Pass 1: grip targets (wrist position, finger direction, palm normal) per frame.
t, around = cfg.get("t", 0.75), math.radians(cfg.get("around_deg", 50))
targets = {s: [] for s in SIDES}
if SHAFT or BALLS:
    G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]

    def shaft():
        base = G.matrix_world @ G.pose.bones["penis_01"].head
        return base, (G.matrix_world @ G.pose.bones["penis_04"].tail - base).normalized()
if SHAFT:
    def palm(s):
        return (head(s + "_hand") + head(s + "_middle1")) / 2

    # The SLAL stroke: the palm's position along the shaft, then its 5..95 % range.
    along = {s: [] for s in "lr"}
    for g in frames:
        sc.frame_set(g)
        base, axis = shaft()
        for s in "lr":
            along[s].append((palm(s) - base).dot(axis))
    span = {}
    for s in "lr":
        a = sorted(along[s])
        span[s] = (a[len(a) // 20], a[-1 - len(a) // 20])
        print("HANDS %s SLAL stroke %.3f..%.3f m" % (s, *span[s]))
    s0, s1 = cfg.get("stroke", (0.045, 0.095))
    # Stroke fraction per frame. "ease_jumps": N replaces +-N frames round each SLAL clip seam
    # (the palm jumps half a stroke in one frame, at f120 and f360) by a smoothstep across it.
    kc = {}
    for s in "lr":
        lo_a, hi_a = span[s]
        k = [min(1.0, max(0.0, (a - lo_a) / max(hi_a - lo_a, 1e-6))) for a in along[s]]
        n = cfg.get("ease_jumps", 0)
        for j in [j for j in range(1, len(k)) if n and abs(k[j] - k[j - 1]) > 0.2]:
            a, b = max(0, j - n), min(len(k) - 1, j + n)
            for m in range(a + 1, b):
                x = (m - a) / (b - a)
                k[m] = k[a] + (k[b] - k[a]) * x * x * (3 - 2 * x)
            print("HANDS %s eased jump at f%d" % (s, frames[j]))
        kc[s] = k
for i, g in enumerate(frames):
    sc.frame_set(g)
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(body, dg) if body else None
    inv = body.matrix_world.inverted() if body else None
    for s in SIDES:
        if BALLS:
            base, axis = shaft()
            up = Vector((0, 0, 1))
            fwd = (axis - up * axis.dot(up)).normalized()
            bf, bl, bu = cfg.get("balls", (-0.024, 0.0, -0.055))
            c = base + fwd * bf + up.cross(fwd) * bl + up * bu
            hit = bvh.ray_cast(inv @ (c - up * 0.12), (inv.to_3x3() @ up).normalized(), 0.12)[0] if bvh else None
            surf = body.matrix_world @ hit if hit else c - up * 0.035
            targets[s].append((surf - up * 0.012 + fwd * 0.045, -fwd, up))
            continue
        if SHAFT:
            base, axis = shaft()
            src = cfg.get("rhythm", s)    # "rhythm": "r" strokes this hand with the SLAL right hand's timing
            k = kc[src][i]
            q = base + axis * (s0 + k * (s1 - s0))
            if POSE:
                H = pose_frame(POSE[s], q, axis, head(s + "_bicep"))
                # "twist_deg": the hand rolls round the shaft with the stroke, +-half at the ends.
                H = Matrix.Rotation(math.radians(cfg.get("twist_deg", 0)) * (k - 0.5), 3, axis) @ H
                c = H @ Vector(POSE[s]["centre"])
                # "squeeze": move the hand this far in toward the shaft axis (the ring is wider than the shaft).
                c -= (c - axis * c.dot(axis)).normalized() * cfg.get("squeeze", 0.0)
                targets[s].append((q - c, H @ hand_axes[s][0], H @ hand_axes[s][1]))
                continue
            d = palm(s) - q
            d = (d - axis * d.dot(axis)).normalized()     # the side her palm comes from
            if cfg.get("approach") == "shoulder":
                # Palm on the side where the fingers point away from her shoulder, so the
                # forearm runs on in line with the hand instead of meeting it at 90 deg.
                sh = head(s + "_bicep") - q
                sh = (sh - axis * sh.dot(axis)).normalized()
                for c in (axis.cross(sh), sh.cross(axis)):
                    w = axis.cross(c)
                    if thumb_sign[s] * w.cross(-c).dot(axis) < 0:
                        w = -w
                    if w.dot(sh) < 0:
                        d = c.normalized()
            hit = None
            if bvh:
                hit = bvh.ray_cast(inv @ (q + d * 0.06), (inv.to_3x3() @ -d).normalized(), 0.06)[0]
            surf = body.matrix_world @ hit if hit else q + d * cfg.get("radius", 0.019)
            # Fingers wrap round the shaft; pick the way round that puts the thumb toward the tip.
            wrap = axis.cross(d).normalized()
            if thumb_sign[s] * wrap.cross(-d).dot(axis) < 0:
                wrap = -wrap
            targets[s].append((surf + d * cfg.get("palm_off", 0.012) - wrap * cfg.get("wrist_back", 0.045), wrap, -d))
            continue
        # "leg_of": another armature (Geralt) and "leg_side": its l/r leg, to rest the hand on his thigh.
        A = bpy.data.objects[cfg["leg_of"]] if cfg.get("leg_of") else None
        ls = cfg.get("leg_side", s)
        if A:
            hip, knee = (A.matrix_world @ A.pose.bones[ls + n].head for n in ("_thigh", "_shin"))
        else:
            hip, knee = head(s + "_thigh"), head(s + "_shin")
        axis = (knee - hip).normalized()
        q = hip.lerp(knee, t)
        back = side_vec(s, (0, -1, 0), ls + "_thigh", A)          # faces +Y at rest
        out = side_vec(s, (-1 if ls == "l" else 1, 0, 0), ls + "_thigh", A)   # left is -X
        d = back * math.cos(around) + out * math.sin(around)
        d = (d - axis * d.dot(axis)).normalized()
        o, ld = inv @ (q + d * 0.2), (inv.to_3x3() @ -d).normalized()
        hit = bvh.ray_cast(o, ld, 0.25)[0]                     # from outside, back toward the axis
        surf = body.matrix_world @ hit if hit else q + d * 0.065
        # Fingers wrap from the grip side round toward the back/inner side of the leg.
        wrap = axis.cross(d).normalized()
        inner = -out
        if wrap.dot(back * math.sin(around) + inner * math.cos(around)) < 0:
            wrap = -wrap
        palm_n = -d
        wrist = surf + d * 0.012 - wrap * 0.045
        targets[s].append((wrist, wrap, palm_n))

half = cfg.get("smooth", 4)
for s in SIDES:
    cols = list(zip(*targets[s]))
    cols = [smooth_list(list(c), half) for c in cols]
    targets[s] = [(w, f.normalized(), n.normalized()) for w, f, n in zip(*cols)]


def rotate_about(pb, R, pivot_world):
    """Pre-multiply the bone's pose by world rotation R about pivot; pose matrices are armature space."""
    A3 = AW.to_3x3().normalized()
    Ra = (A3.inverted() @ R.normalized() @ A3).to_4x4()
    p = AW.inverted() @ pivot_world
    pb.matrix = Matrix.Translation(p) @ Ra @ Matrix.Translation(-p) @ pb.matrix
    # Scale is not keyed, so it persists across frames: rounding would build up into a
    # sheared, then exploded hand (seen by frame 109). Pin it.
    pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()


def twist_angle(q, axis):
    v = Vector((q.x, q.y, q.z))
    return 2 * math.atan2(v.dot(axis), q.w)


keys = {}
names = []
for s in SIDES:
    names += [s + "_bicep", s + "_forearm", s + "_hand", s + "_forearmRoll1", s + "_forearmRoll2", s + "_handRoll"]
    names += ["%s_%s%d" % (s, f, j) for f in FINGERS for j in (1, 2, 3)] + [s + "_thumb1", s + "_thumb2", s + "_thumb3"]
    if POSE:
        names += [n for n in POSE[s]["quats"] if n not in names]
names =[n for n in names if n in pbs]
for n in names:
    keys[n] = {}
reach_short = 0
L = {}
for s in SIDES:
    L[s] = ((bones[s + "_forearm"].head_local - bones[s + "_bicep"].head_local).length,
            (bones[s + "_hand"].head_local - bones[s + "_forearm"].head_local).length)
pole_out, pole_down = cfg.get("pole", (1.0, -0.6))
curl = [math.radians(a) for a in cfg.get("curl_deg", (25, 25, 20))]
thumb = [math.radians(a) for a in cfg.get("thumb_deg", (0, 10, 10))]


def flex_quats(s):
    """Each finger joint's keyed rotation: about its own (bone Y x palm side) axis, in its
    rest frame. W3 finger bones do not share one roll, so the axis is found per bone."""
    palm_rest = rest_rot(s + "_hand") @ hand_axes[s][1]
    out = {}
    for fn in FINGERS + ("thumb",):
        for j, ang in zip((1, 2, 3), thumb if fn == "thumb" else curl):
            bn = "%s_%s%d" % (s, fn, j)
            if bn in pbs:
                # The thumb opposes: it closes toward the middle finger, not the palm.
                aim = bones[s + "_middle2"].head_local - bones[bn].head_local if fn == "thumb" else palm_rest
                k = Vector((0, 1, 0)).cross(rest_rot(bn).inverted() @ aim)
                out[bn] = Quaternion(k.normalized(), ang) if k.length > 1e-4 else Quaternion()
    return out


flex = {s: flex_quats(s) for s in SIDES}
gap = cfg.get("wrap_gap")    # finger radius: curl each joint until its tip is this far off the shaft
solved = {}                  # bone -> solved curl angle per frame, smoothed before keying
thumb_q = {}                 # thumb bone -> solved local rotation per frame (not one fixed axis)
tilt = math.radians(cfg.get("thumb_axial_deg", 70))   # thumb heading off the shaft axis


def tip_gap(bvh, inv, base, q, length):
    """Signed distance of the bone's tail from the shaft skin with local rotation q."""
    p = inv @ (AW @ (base @ q.to_matrix().to_4x4() @ Vector((0, length, 0))))
    loc, nrm, _, d = bvh.find_nearest(p)
    return d if (p - loc).dot(nrm) > 0 else -d


def wrap_thumb(j, base, length, bvh, inv, wrap):
    """The thumb's own curl closes it toward the middle finger, i.e. into the shaft, so it lay
    along the shaft with its tip past the glans. Steer it round the shaft instead, the other
    way to the fingers: the first joint swings in the skin's tangent plane, the outer two
    then bend toward the skin until the tip is `gap` off it."""
    sb, sax = shaft()
    B = AW.to_3x3().normalized() @ base.to_3x3().normalized()
    y = B @ Vector((0, 1, 0))
    r = AW @ base.translation - sb
    out = (r - sax * r.dot(sax)).normalized()
    if j == 1:
        t = (-wrap - out * (-wrap).dot(out)).normalized()
        R = y.rotation_difference(t * math.sin(tilt) + sax * math.cos(tilt)).to_matrix()
        return (B.inverted() @ R @ B).to_quaternion()
    k = B.inverted() @ out.cross(y).normalized()      # +angle bends the tip into the skin
    best, a = 0.0, 0.0
    while a <= math.radians(90) and tip_gap(bvh, inv, base, Quaternion(k, a), length) >= gap:
        best, a = a, a + math.radians(5)
    return Quaternion(k, best)


def wrap_fingers(s, bvh, inv, wrap):
    """Per-frame curl: each joint, knuckle first, bends as far as it can while its tip stays
    `gap` off the deformed shaft. FK by hand so the search needs no scene updates."""
    for fn in FINGERS + ("thumb",):
        M = None
        for j in (1, 2, 3):
            bn = "%s_%s%d" % (s, fn, j)
            if bn not in flex[s]:
                break
            pb, b = pbs[bn], bones[bn]
            if M is None:
                M = pb.parent.matrix
                Mp_rest = b.parent.matrix_local
            base = M @ (Mp_rest.inverted() @ b.matrix_local)
            if fn == "thumb":
                q = wrap_thumb(j, base, b.length, bvh, inv, wrap)
                thumb_q.setdefault(bn, []).append(Vector(q))
            else:
                # Start straight: a joint already touching stays straight, never bent back.
                ax, full = flex[s][bn].axis, flex[s][bn].angle
                best, a = 0.0, 0.0
                while a <= max(full, math.radians(100)) and tip_gap(bvh, inv, base, Quaternion(ax, a), b.length) >= gap:
                    best, a = a, a + math.radians(5)
                q = Quaternion(ax, best)
                solved.setdefault(bn, []).append(best)
            pb.rotation_quaternion = q
            M, Mp_rest = base @ q.to_matrix().to_4x4(), b.matrix_local

close = cfg.get("close")     # bone-to-shaft gap the vanilla pose's fingers are closed (thumb opened) to
closed = {}                  # bone -> extra curl per frame, smoothed before keying


def close_pose(s, bvh, inv):
    """The vanilla grip rings a thicker handle than the shaft. Knuckle first, each finger
    joint of the vanilla pose bends further (or, already sunk in, opens) until its tail is
    `close` off the skin, so every segment lies on the shaft rather than only the tips.
    The thumb's curl aims at the middle finger, i.e. into the shaft, so it only opens, by
    one angle shared by its three joints (per joint it kinked and stuck out)."""
    for fn in FINGERS + ("thumb",):
        chain = ["%s_%s%d" % (s, fn, j) for j in (1, 2, 3)]
        chain = [bn for bn in chain if bn in flex[s] and bn in POSE[s]["quats"]]
        if not chain:
            continue

        def gaps(angs):
            """Tail gaps of the chain posed with the extra curls angs (FK from its parent)."""
            M, Mp, out = pbs[chain[0]].parent.matrix, bones[chain[0]].parent.matrix_local, []
            for bn, a in zip(chain, angs):
                base = M @ (Mp.inverted() @ bones[bn].matrix_local)
                q = Quaternion(flex[s][bn].axis, a) @ Quaternion(POSE[s]["quats"][bn])
                out.append(tip_gap(bvh, inv, base, q, bones[bn].length))
                M, Mp = base @ q.to_matrix().to_4x4(), bones[bn].matrix_local
            return out
        step = math.radians(2)
        if fn == "thumb":
            a = 0.0
            while min(gaps([a] * len(chain))) < close and a > math.radians(-30):
                a -= step
            angs = [a] * len(chain)
            # "thumb_tuck": the opened tip runs off the shaft on a tangent, so the outer
            # joints bend back in (at most this many degrees) until within "thumb_close" of the skin.
            for k in range(1, len(chain)):
                while gaps(angs[:k] + [angs[k] + step])[k] >= cfg.get("thumb_close", close) and angs[k] < a + math.radians(cfg.get("thumb_tuck", 0)):
                    angs[k] += step
        else:
            angs = []
            for k in range(len(chain)):
                a = 0.0
                if gaps(angs + [a])[-1] < close:
                    while gaps(angs + [a])[-1] < close and a > math.radians(-30):
                        a -= step
                else:
                    while gaps(angs + [a + step])[-1] >= close and a < math.radians(40):
                        a += step
                angs.append(a)
        for bn, a in zip(chain, angs):
            closed.setdefault(bn, []).append(a)
            pbs[bn].rotation_quaternion = Quaternion(flex[s][bn].axis, a) @ Quaternion(POSE[s]["quats"][bn])


for i, g in enumerate(frames):
    sc.frame_set(g)
    for s in SIDES:
        W, f, n = targets[s][i]
        S = head(s + "_bicep")
        L1, L2 = L[s]
        dvec = W - S
        d = dvec.length
        if d > 0.995 * (L1 + L2):
            reach_short += 1
            d = 0.995 * (L1 + L2)
        d = max(d, abs(L1 - L2) + 0.01)
        u = dvec.normalized()
        out = side_vec(s, (-1 if s == "l" else 1, 0, 0), "torso2")
        pole = out * pole_out + Vector((0, 0, pole_down))
        pole = (pole - u * pole.dot(u)).normalized()
        a = (L1 * L1 - L2 * L2 + d * d) / (2 * d)
        E = S + u * a + pole * math.sqrt(max(0.0, L1 * L1 - a * a))
        Wc = S + u * d
        # Upper arm, then forearm: shortest rotation that aims each at its new joint.
        cur = head(s + "_forearm") - S
        rotate_about(pbs[s + "_bicep"], cur.rotation_difference(E - S).to_matrix(), S)
        cur = head(s + "_hand") - head(s + "_forearm")
        rotate_about(pbs[s + "_forearm"], cur.rotation_difference(Wc - E).to_matrix(), head(s + "_forearm"))
        # Hand: carry its (finger, palm) frame onto the target frame about the wrist.
        hf, hn = hand_axes[s]
        Rw = rot_world(s + "_hand")
        R = frame_of(f, n) @ frame_of(Rw @ hf, Rw @ hn).inverted()
        fa = rot_world(s + "_forearm")
        rel_before = fa.inverted() @ Rw
        rotate_about(pbs[s + "_hand"], R, head(s + "_hand"))
        rel_after = fa.inverted() @ rot_world(s + "_hand")
        fax = (fa.inverted() @ (head(s + "_hand") - head(s + "_forearm"))).normalized()
        tw = twist_angle((rel_after @ rel_before.inverted()).to_quaternion(), fax)
        # Roll bones follow the forearm rigidly, then take their share of the twist.
        axis_w = (head(s + "_hand") - head(s + "_forearm")).normalized()
        for rn, w in ((s + "_forearmRoll1", 1 / 3), (s + "_forearmRoll2", 2 / 3), (s + "_handRoll", 1.0)):
            if rn not in pbs:
                continue
            pb = pbs[rn]
            rest_rel = bones[s + "_forearm"].matrix_local.inverted() @ bones[rn].matrix_local
            pb.matrix = pbs[s + "_forearm"].matrix @ rest_rel
            pb.scale = (1, 1, 1)
            bpy.context.view_layer.update()
            rotate_about(pb, Matrix.Rotation(tw * w, 3, axis_w), head(rn))
        # Fingers: replace the SLAL fists by rest + a bend of curl_deg toward the palm.
        for bn, q in (POSE[s]["quats"].items() if POSE else flex[s].items()):
            pbs[bn].rotation_quaternion = q
        bpy.context.view_layer.update()
        if close is not None and POSE and SHAFT:
            close_pose(s, BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get()), body.matrix_world.inverted())
            bpy.context.view_layer.update()
        if gap is not None and SHAFT and body:
            wrap_fingers(s, BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get()), body.matrix_world.inverted(), f)
            bpy.context.view_layer.update()
    for nm in names:
        q = pbs[nm].rotation_quaternion.copy()
        prev = keys[nm].get(g - 1)
        if prev is not None and q.dot(Quaternion(prev)) < 0:
            q.negate()
        keys[nm][g] = tuple(q)

# The per-frame curl search flips between contact and no contact on some frames:
# median drops those one-frame pops, then the moving average evens out the 5 deg steps.
for bn, angs in solved.items():
    med = [sorted(angs[max(0, i - 4):i + 5])[len(angs[max(0, i - 4):i + 5]) // 2] for i in range(len(angs))]
    for g, a in zip(frames, smooth_list(med, 3)):
        keys[bn][g] = tuple(Quaternion(flex[bn[0]][bn].axis, a))
for bn, angs in closed.items():
    med = [sorted(angs[max(0, i - 4):i + 5])[len(angs[max(0, i - 4):i + 5]) // 2] for i in range(len(angs))]
    sm = smooth_list(med, 3)
    print("HANDS close %s extra curl %.0f..%.0f deg" % (bn, math.degrees(min(sm)), math.degrees(max(sm))))
    for g, a in zip(frames, sm):
        keys[bn][g] = tuple(Quaternion(flex[bn[0]][bn].axis, a) @ Quaternion(POSE[bn[0]]["quats"][bn]))
for bn, qs in thumb_q.items():
    for i in range(1, len(qs)):
        if qs[i].dot(qs[i - 1]) < 0:
            qs[i].negate()
    for g, v in zip(frames, smooth_list(qs, 3)):
        keys[bn][g] = tuple(v.normalized())
for nm in names:
    write(P, nm, "rotation_quaternion", keys[nm])
print("HANDS reach-limited samples", reach_short, "of", 2 * len(frames))
for g in frames[::60]:
    sc.frame_set(g)
    i = g - lo
    print("HANDS f=%3d" % g, " ".join("%s wrist err %.3f" % (s, (head(s + "_hand") - targets[s][i][0]).length) for s in SIDES))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
