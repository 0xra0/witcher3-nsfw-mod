"""Shared crotch re-weight for the prostitute body (twals_03_wa__body), rest model space.

Her vulva is the crotch FLOOR, z 0.915-0.955, y 0.005 (perineum) .. 0.09 (clitoris): that is
where FemaleTexturesRR paints it (UV u 0.685, v 0.016-0.066; vaginal opening about
(0, 0.036, 0.921)). Vanilla skins it ~50% pelvis + both thighs, so flexed hips drag it.
The vertical midline strip BELOW it (x~0, y~0.03, z 0.78-0.92) is where the inner thighs
meet, ~95% one thigh; v3-v6 mistook it for the entrance and must stay thigh-skinned.
crotch(q) is how much of a vertex moves over to the pelvis bone: 1 on the vulva, fading
out toward the inner thighs and above/below. Used by
reweight_crotch.py (cooked .1.buffer) and blender/reweight_her.py (the scene copy), so both
skin the same way.
"""


def _ramp(v, full, zero):
    """1 at |v| <= full, 0 at |v| >= zero, smooth in between."""
    v = abs(v)
    if v <= full:
        return 1.0
    if v >= zero:
        return 0.0
    u = (zero - v) / (zero - full)
    return u * u * (3 - 2 * u)


def crotch(q):
    x, y, z = q
    # Wide falloffs: with her legs spread the skin between the rigid vulva and the thighs
    # must stretch, and a short ramp tears it into spikes (seen at 3.5 cm).
    fx = _ramp(x, 0.02, 0.09)
    fz = _ramp(z - 0.935, 0.025, 0.10)         # full 0.91..0.96, zero below 0.835 / above 1.035
    fy = _ramp(y - 0.045, 0.06, 0.12)          # full -0.015..0.105 (perineum..clitoris)
    return fx * fz * fy


def blend(weights, pelvis, c):
    """weights: {bone: w} summing to 1. Moves fraction c of every non-pelvis weight to pelvis."""
    out = {b: w * (1 - c) for b, w in weights.items() if b != pelvis}
    out[pelvis] = weights.get(pelvis, 0.0) + c * (1 - weights.get(pelvis, 0.0))
    return out
