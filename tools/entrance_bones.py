"""Shared entrance ring for the prostitute body (twals_03_wa__body), rest model space.

Six bones (vag_0..vag_5, children of pelvis with pelvis's orientation) sit on a 1.5 cm
circle round the vaginal opening, in the plane across her canal. The skin round the
opening is moved from her pelvis onto them, so translating bone k by open * dir(k) opens
a hole of radius ~open, and translating them all along the canal drags the lips in/out.
Used by tools/skin_entrance.py (cooked mesh + rig) and blender/open_entrance.py (the
scene copy), so the game and the previews skin the same way.
"""
import math

E0 = (0.0, 0.036, 0.921)                     # opening (crotch_weights.py)
_c = (0.0, -0.3, 1.0)                        # canal, pointing into her body
_n = math.sqrt(sum(v * v for v in _c))
CANAL = tuple(v / _n for v in _c)
SIDE = (1.0, 0.0, 0.0)                       # her left/right (x), already across the canal
FRONT = (0.0, CANAL[2], -CANAL[1])           # CANAL x SIDE: toward the clitoris (+y)
N = 6
NAMES = ["vag_%d" % k for k in range(N)]
R_BONE = 0.015
O_DESIGN = 0.022                             # hole radius the weights are shaped for
P_HUG = 3                                    # r_new = (r^p + o^p)^(1/p): only skin inside the shaft moves
R_CUT = 0.05                                 # no ring weight beyond this radius
A_FULL, A_ZERO = 0.02, 0.05                  # along the canal (the vulva floor is curved)
# Lip ring (vagl_0..vagl_5): the skin just outside the shaft, the part the POV camera
# actually sees. The inner ring only moves skin the shaft then hides, so on its own the
# stretch was invisible in game; these bones drag the rim in and out with the stroke and
# puff it outward on the pull, the way Unicorn's entrance tugs.
LIP_NAMES = ["vagl_%d" % k for k in range(N)]
ALL = NAMES + LIP_NAMES
R_LIP = 0.03
LIP_IN = (0.008, 0.016)                      # weight rises over this radius ...
LIP_OUT = (0.036, 0.058)                     # ... and falls over this one
LIP_AX = (0.03, 0.055)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def angle(k):
    return 2 * math.pi * k / N


def direction(k):
    """Unit outward direction of bone k, rest model space."""
    a = angle(k)
    return tuple(math.cos(a) * s + math.sin(a) * f for s, f in zip(SIDE, FRONT))


def position(k, r=R_BONE):
    return tuple(e + r * d for e, d in zip(E0, direction(k)))


def bone_position(name):
    """Rest model-space head of any ring bone (vag_k or vagl_k)."""
    if name in LIP_NAMES:
        return position(LIP_NAMES.index(name), R_LIP)
    return position(NAMES.index(name))


def _ramp(v, full, zero):
    v = abs(v)
    if v <= full:
        return 1.0
    if v >= zero:
        return 0.0
    u = (zero - v) / (zero - full)
    return u * u * (3 - 2 * u)


def _polar(q):
    d = [a - b for a, b in zip(q, E0)]
    x, y = _dot(d, SIDE), _dot(d, FRONT)
    return math.hypot(x, y), math.atan2(y, x), _dot(d, CANAL)


def _lobes(th, W):
    """Split W between the two bones either side of angle th (the game skins 4 bones per
    vertex, so two per ring leaves room for both rings)."""
    a = (th / (2 * math.pi / N)) % N
    k0 = int(a) % N
    u = a - int(a)
    out = {k0: W * (1 - u), (k0 + 1) % N: W * u}
    return {k: w for k, w in out.items() if w > 1e-3 * max(W, 1e-9)}


def lip(q):
    """{k: w} share of a rest vertex for the lip bones, before the inner ring's share."""
    r, th, ax = _polar(q)
    W = (1 - _ramp(r - LIP_IN[0], 0, LIP_IN[1] - LIP_IN[0]) if r > LIP_IN[0] else 0.0)
    W *= _ramp(r, *LIP_OUT) * _ramp(ax, *LIP_AX)
    return _lobes(th, W) if W >= 1e-3 else {}


def ring(q):
    """{k: w} share of a rest vertex that goes to the ring bones (sums to <= 1)."""
    d = [a - b for a, b in zip(q, E0)]
    ax = _dot(d, CANAL)
    x, y = _dot(d, SIDE), _dot(d, FRONT)
    # Opening by o moves a vertex at radius r out to (r^p + o^p)^(1/p): skin inside the
    # shaft goes to its surface, skin already outside barely moves (a wide linear falloff
    # swelled the whole vulva 2 cm toward the clitoris). The weight is that shift / o.
    r, o = math.hypot(x, y), O_DESIGN
    W = ((r ** P_HUG + o ** P_HUG) ** (1 / P_HUG) - r) / o
    W *= _ramp(r, 0.6 * R_CUT, R_CUT) * _ramp(ax, A_FULL, A_ZERO)
    if W < 1e-3:
        return {}
    return _lobes(math.atan2(y, x), W)


def take(weights, pelvis, q):
    """weights {bone: w} summing to 1 -> new weights with part of PELVIS's share moved onto
    the ring bones ("vag_k" / "vagl_k" keys). Only the pelvis share moves: with the rings
    at rest the vertex follows exactly what it followed before. The lip ring takes its
    share of what the inner ring leaves."""
    r, l = ring(q), lip(q)
    p = weights.get(pelvis, 0.0)
    if not (r or l) or p < 1e-3:
        return weights
    out = dict(weights)
    moved, inner = 0.0, sum(r.values())
    for names, share, scale in ((NAMES, r, 1.0), (LIP_NAMES, l, 1.0 - inner)):
        for k, w in share.items():
            out[names[k]] = p * w * scale
            moved += p * w * scale
    out[pelvis] = p - moved
    return limit(out, pelvis)


def limit(w, pelvis, n=4):
    """Keep the n largest weights (the game's limit). A dropped ring weight is folded into
    the largest kept pelvis/ring weight: at rest the rings sit on pelvis, so the rest pose
    is unchanged and only that bit of the opening's pull is lost."""
    w = {b: v for b, v in w.items() if v > 1e-4}
    if len(w) <= n:
        return w
    keep = sorted(w, key=lambda b: -w[b])[:n]
    drop = sum(v for b, v in w.items() if b not in keep)
    out = {b: w[b] for b in keep}
    same = [b for b in keep if b == pelvis or b in ALL]
    if same:
        out[same[0]] += drop
    else:
        out = {b: v / (1 - drop) for b, v in out.items()}
    return out
