"""Headless: spread one-frame pose pops (both actors) over a few frames either side.

  blender -b in.blend --python smooth_pops.py -- pops.json out.blend

pops.json:
  {"min_jump": 0.015,     # pelvis world travel in one frame that counts as a pop (m)
   "ratio": 3.0,          # ... and at least this many times the local median speed
   "half": 6}             # frames either side over which the jump is spread

The retargeted SLAL stages meet inside a shot: at frame 120 his pelvis drops 3.3 cm in
one frame and the penis, aimed off both bodies, flicks 42 deg. For every keyed channel of
both armatures the excess step at a pop (the step minus the mean of its neighbours) is
taken out: half absorbed before the pop, half after, with smoothstep ramps, so curves stay
continuous and the motion either side is kept. Run after stroke.py, before bend_penis.py
(the penis, hands and camera are then solved on the smoothed bodies)."""
import json, os, sys
import bpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nla_keys import _fcurves, frame_range, track

CFG, OUT = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(CFG))
ACTORS = [bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"],
          bpy.data.objects["prostitute:CMovingPhysicalAgentComponent2_ARM"]]
sc = bpy.context.scene
lo, hi = frame_range(ACTORS[0])
frames = list(range(lo, hi + 1))
half = cfg.get("half", 6)

# Detect pops on the evaluated pelvis of either actor.
pos = {A.name: [] for A in ACTORS}
for g in frames:
    sc.frame_set(g)
    for A in ACTORS:
        pos[A.name].append(A.matrix_world @ A.pose.bones["pelvis"].head)
pops = set()
for A in ACTORS:
    p = pos[A.name]
    sp = [0.0] + [(p[i] - p[i - 1]).length for i in range(1, len(p))]
    for i in range(2, len(sp) - 1):
        nb = sorted(sp[max(1, i - 10):i] + sp[i + 1:i + 11])
        med = nb[len(nb) // 2]
        if sp[i] > cfg.get("min_jump", 0.015) and sp[i] > cfg.get("ratio", 3.0) * med:
            pops.add(frames[i])
# A pop seen on consecutive frames is one pop; keep the bigger step.
pops = sorted(pops)
print("POPS", pops)


def channels(A):
    """{(data_path, index): {frame: value}} read from every strip (shared boundary frames agree)."""
    out = {}
    for strip in track(A).strips:
        g0 = int(round(strip.frame_start))
        for fc in _fcurves(strip.action):
            d = out.setdefault((fc.data_path, fc.array_index), {})
            for j, kp in enumerate(fc.keyframe_points):
                d[min(hi, g0 + j)] = kp.co[1]
    return out


def put(A, vals):
    for strip in track(A).strips:
        g0 = int(round(strip.frame_start))
        for fc in _fcurves(strip.action):
            d = vals[(fc.data_path, fc.array_index)]
            for j, kp in enumerate(fc.keyframe_points):
                kp.co[1] = d[min(hi, g0 + j)]
            fc.update()


def ss(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


for A in ACTORS:
    ch = channels(A)
    # Quaternion sign continuity first, so a sign flip is not mistaken for a pop.
    for path in {p for p, i in ch if p.endswith("rotation_quaternion")}:
        q = [ch.get((path, i)) for i in range(4)]
        if None in q:
            continue
        for k in range(1, len(frames)):
            g, g1 = frames[k], frames[k - 1]
            if sum(q[i][g] * q[i][g1] for i in range(4)) < 0:
                for i in range(4):
                    q[i][g] = -q[i][g]
    worst = 0.0
    for J in pops:
        if J - 2 < lo or J + 1 > hi:
            continue
        for key, v in ch.items():
            step = v[J] - v[J - 1]
            expect = 0.5 * ((v[J - 1] - v[J - 2]) + (v[J + 1] - v[J]))
            dl = step - expect
            if abs(dl) < 1e-6:
                continue
            worst = max(worst, abs(dl)) if key[0].endswith("location") else worst
            for f in range(max(lo, J - half), J):
                v[f] += 0.5 * dl * ss((f - (J - half) + 1) / half)
            for f in range(J, min(hi, J + half - 1) + 1):
                v[f] -= 0.5 * dl * ss((J + half - f) / half)
    put(A, ch)
    print("POPS %s: largest location step removed %.3f" % (A.name.split(":")[0], worst))

for J in pops:
    out = []
    for g in (J - 1, J, J + 1):
        sc.frame_set(g)
        out.append(ACTORS[0].matrix_world @ ACTORS[0].pose.bones["pelvis"].head)
    print("POPS check f=%d his pelvis step before %.3f now %.3f" % (
        J, (pos[ACTORS[0].name][J - lo] - pos[ACTORS[0].name][J - 1 - lo]).length, (out[1] - out[0]).length))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
