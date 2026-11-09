"""Move the thigh share of the skin around her opening onto the pelvis, in torso AND legs.

  python3 -I tools/crotch_pelvis.py torso.w2mesh torso.info.json legs.w2mesh legs.info.json \
      out_torso.w2mesh out_legs.w2mesh [r_in r_out]

The crotch floor of twa0_01 (and the leg piece welded to it, ls_02_wa__body_barefoot) is
skinned ~60% to l_/r_thigh only 1-2.5 cm from the opening, as in retail. In the cowgirl
squat the thighs swing so far that this skin was dragged up to 13 cm off the pelvis: a flat
sliced panel beside the shaft and a ragged lump under the vulva. Here every vertex within
r_out of E0 (default 2 -> 5.5 cm, smoothstep) hands that share of thigh/legRoll weight to
the pelvis. The weights are a function of position and bone names only, so the torso and
leg copies of a seam vertex get identical skin and the weld seam_lock.py made stays closed.
Ring and lip bones are untouched; positions, normals and counts stay as they are.
"""
import json, os, shutil, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "work", "scratch", "bones")]
from mesh_geo import Mesh
import entrance_bones as eb
from seam_lock import pack, smooth, WELD

RETAIL_N = 1785          # twa0_01 LOD0 vertices before sculpt_vulva appended its own
LEG = {"l_thigh", "r_thigh", "l_legRoll", "r_legRoll", "l_legRoll2", "r_legRoll2"}


def named(row, names):
    w = {}
    for b, v in zip(row[8:12], row[12:16]):
        if v:
            w[names[int(b)]] = w.get(names[int(b)], 0.0) + v / 255.0
    return w


def outline_dist(P, Q):
    """Distance of each point in P to the closed polyline Q."""
    d = np.full(len(P), np.inf)
    for a, b in zip(Q, np.roll(Q, -1, 0)):
        t = np.clip((P - a) @ (b - a) / ((b - a) @ (b - a)), 0, 1)
        d = np.minimum(d, np.linalg.norm(P - (a + t[:, None] * (b - a)), axis=1))
    return d


def relax(m, names, r_in, r_out, sculpt=None):
    """sculpt=(first sculpt vertex, outline vertex ids, fade m): LOD0 sculpt vertices only,
    faded in from the retail outline, so retail and leg skin are not touched."""
    idx = {n: i for i, n in enumerate(names)}
    E0 = np.array(eb.E0)
    for k, ch in enumerate(m.chunks):
        P = m.positions(k)
        f = smooth(r_in, r_out, np.linalg.norm(P - E0, axis=1))
        if sculpt:
            if k:
                break
            first, bound, fade = sculpt
            f = np.maximum(f, 1 - smooth(0.0, fade, outline_dist(P, P[bound])))
            f[:first] = 1
        changed = 0
        for i in np.where(f < 1 - 1e-4)[0]:
            w = named(ch["coords"][i], names)
            moved = sum(v for n, v in w.items() if n in LEG) * (1 - f[i])
            if moved < 1e-4:
                continue
            w = {n: (v * f[i] if n in LEG else v) for n, v in w.items()}
            w["pelvis"] = w.get("pelvis", 0.0) + moved
            bn, bw = pack(w)
            ch["coords"][i][8:12] = [idx[n] if v else 0 for n, v in zip(bn, bw)]
            ch["coords"][i][12:16] = bw
            changed += 1
        print("LOD%d: %d verts reskinned within %.3f m" % (k, changed, r_out))


def save_skin(m, src, dst):
    """Write m's coords rows into a copy of src's own buffer. Mesh.save re-lays the buffer
    and always emits a vertex-colour stream, which ls_02 does not have (offset 0); only the
    skin bytes change here, so the header is copied as is."""
    buf = bytearray(m.buf)
    for r, ch in zip(m.rc, m.chunks):
        c = ch["coords"].tobytes()
        buf[r[1]:r[1] + len(c)] = c
    shutil.copyfile(src, dst)
    open(dst + ".1.buffer", "wb").write(bytes(buf))


def main():
    tp, ti, lp, li, to, lo = sys.argv[1:7]
    r_in, r_out = (float(x) for x in sys.argv[7:9]) if len(sys.argv) > 8 else (0.02, 0.055)
    tn, ln = json.load(open(ti))["bones"] + eb.ALL, json.load(open(li))["bones"]
    t, l = Mesh.load(tp), Mesh.load(lp)
    if os.environ.get("SCULPT_ONLY"):
        import sculpt_vulva
        bound = sculpt_vulva.TARGETS["twa0_01_wa__body"][0]
        relax(t, tn, r_in, r_out, (RETAIL_N, bound, float(os.environ["SCULPT_ONLY"])))
    else:
        relax(t, tn, r_in, r_out)
        relax(l, ln, r_in, r_out)
    for k in range(min(len(t.chunks), len(l.chunks))):
        T, L = t.positions(k), l.positions(k)
        bad = n = 0
        for j, q in enumerate(L):
            d = np.linalg.norm(T - q, axis=1)
            i = d.argmin()
            if d[i] < WELD:
                n += 1
                a, b = named(t.chunks[k]["coords"][i], tn), named(l.chunks[k]["coords"][j], ln)
                bad += any(abs(a.get(x, 0) - b.get(x, 0)) > 1.5 / 255 for x in set(a) | set(b))
        print("LOD%d seam: %d welded pairs, %d with different skin" % (k, n, bad))
    save_skin(t, tp, to)
    save_skin(l, lp, lo)
    print("->", to, lo)


if __name__ == "__main__":
    main()
