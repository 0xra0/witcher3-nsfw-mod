"""Give her torso's seam with the leg mesh back its retail skin, fading into ours.

  python3 -I tools/seam_lock.py body.w2mesh retail_body.w2mesh legs.w2mesh out.w2mesh [fade_m]
body.w2mesh: the finished torso (sculpt_vulva.py output); retail_body: the same mesh as
shipped (same bone list before the ring bones, same first vertices per LOD); legs: the leg
piece it is worn with (ls_02_wa__body_barefoot), which is skinned like the retail torso.

twa0_01 is a multi-part body: its inner-thigh edge is welded to the legs only by sharing
vertex positions and skin. crotch_weights.crotch() and the ring bones (entrance_bones.take)
moved those edge vertices onto pelvis / vag_* / vagl_*, while the leg copies stayed on the
thighs, so every hip flex and every opening of the ring tore the seam into flat stretched
panels and dark gaps. Here every torso vertex blends from its retail weights at the seam
(exact match with the legs) to its current weights at fade_m from it (default 2.5 cm).
Sculpt vertices with no retail twin take the retail weights of the nearest old vertex.
Only the skin bytes change; positions, normals and counts stay as they are.
"""
import os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "work", "scratch", "bones")]
from mesh_geo import Mesh
import entrance_bones as eb

PELVIS, RING0 = 38, 79   # twa0_01_wa__body bone list (sculpt_vulva.TARGETS)
WELD = 5e-4              # a torso vertex this close to a leg vertex is on the seam


def weights(row):
    w = {}
    for b, v in zip(row[8:12], row[12:16]):
        if v:
            w[int(b)] = w.get(int(b), 0.0) + v / 255.0
    return w


def pack(w):
    s = sorted(((b, v) for b, v in w.items() if v > 1e-3), key=lambda t: -t[1])[:4]
    tot = sum(v for _, v in s)
    qb = [int(round(255 * v / tot)) for _, v in s]
    qb[0] += 255 - sum(qb)
    return [b for b, _ in s] + [0] * (4 - len(s)), qb + [0] * (4 - len(s))


def smooth(a, b, v):
    u = np.clip((v - a) / (b - a), 0, 1)
    return u * u * (3 - 2 * u)


def main():
    src, ret_p, leg_p, dst = sys.argv[1:5]
    fade = float(sys.argv[5]) if len(sys.argv) > 5 else 0.025
    m, ret, leg = Mesh.load(src), Mesh.load(ret_p), Mesh.load(leg_p)
    ring = set(range(RING0, RING0 + len(eb.ALL)))
    for k, ch in enumerate(m.chunks):
        if k >= len(leg.chunks):
            break
        P, R, Q = m.positions(k), ret.positions(k), leg.positions(k)
        nr = len(R)
        assert np.abs(P[:nr] - R).max() < 1e-4, "retail vertices moved in LOD%d" % k
        dl = np.array([np.linalg.norm(Q - p, axis=1).min() for p in P])
        seam = np.where(dl < WELD)[0]
        if not len(seam):
            continue
        ds = np.array([np.linalg.norm(P[seam] - p, axis=1).min() for p in P])
        f = smooth(0.0, fade, ds)
        twin = np.arange(len(P))
        for i in range(nr, len(P)):
            twin[i] = np.linalg.norm(R - P[i], axis=1).argmin()
        changed = 0
        for i in np.where(f < 1 - 1e-4)[0]:
            if f[i] < 1e-6:
                # on the seam: the legs' bytes exactly (retail sums are not always 255)
                bi, bw = (list(ret.chunks[k]["coords"][twin[i]][a:a + 4]) for a in (8, 12))
            else:
                cur, base = weights(ch["coords"][i]), weights(ret.chunks[k]["coords"][twin[i]])
                bi, bw = pack({b: (1 - f[i]) * base.get(b, 0) + f[i] * cur.get(b, 0) for b in set(cur) | set(base)})
            if list(ch["coords"][i][8:16]) != bi + bw:
                ch["coords"][i][8:12], ch["coords"][i][12:16] = bi, bw
                changed += 1
        bad = sum(1 for i in seam if any(b in ring for b, v in weights(ch["coords"][i]).items()))
        print("LOD%d: %d seam verts, %d reskinned within %.3f m, %d seam verts left on ring bones"
              % (k, len(seam), changed, fade, bad))
    m.save(dst)
    print("->", dst)


if __name__ == "__main__":
    main()
