"""Make Geralt's shaft thinner without making it shorter.

  python3 -I tools/slim_shaft.py l_01.w2mesh l_01.info.json out.w2mesh [k]

The l_01_mg__body shaft is ~5.4 cm across, more than twice her whole vulva (~2 cm), so it
cuts through her labia instead of being wrapped by them. A uniform penis-bone scale would
shorten it too (the chain's axis lies in the bones' local x-y plane), so the mesh is
slimmed instead: every vertex skinned to penis_* moves toward the centre of its own slice
across the shaft by factor k (default 0.7), weighted by its penis weight and faded in over
the first 2 cm so the root still meets the body. Slice centres are the per-centimetre
centroids along the rest shaft line, so the shaft keeps its own centre line (the bend /
entry_offset aim stays valid). Only the position bytes change; normals stay (a radial
scale keeps cross-section normals), counts and the rest of the buffer are untouched.
"""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "work", "scratch", "bones")]
from mesh_geo import Mesh
from crotch_pelvis import save_skin

B = np.array([0, 0.095, 0.945])     # rest shaft base / tip, his model space (bend json)
T = np.array([0, 0.24, 1.012])


def main():
    src, info, dst = sys.argv[1:4]
    k = float(sys.argv[4]) if len(sys.argv) > 4 else 0.7
    names = json.load(open(info))["bones"]
    pen = [i for i, n in enumerate(names) if n.startswith("penis_")]
    m = Mesh.load(src)
    for c, ch in enumerate(m.chunks):
        P = m.positions(c)
        C = ch["coords"]
        pw = sum(np.where(np.isin(C[:, 8 + j], pen), C[:, 12 + j] / 255.0, 0) for j in range(4))
        u = (T - B) / np.linalg.norm(T - B)
        t = (P - B) @ u
        sel = pw > 0
        # slice centres every 1 cm, interpolated along t
        knots = np.arange(-0.02, 0.17, 0.01)
        cen = []
        for a in knots:
            s = sel & (np.abs(t - a) < 0.007)
            cen.append(P[s].mean(0) if s.sum() > 8 else B + a * u)
        cen = np.array(cen)
        ctr = np.stack([np.interp(t, knots, cen[:, x]) for x in range(3)], 1)
        off = P - ctr
        off -= np.outer(off @ u, u)                       # across the shaft only
        ramp = np.clip(t / 0.02, 0, 1)
        f = 1 - (1 - k) * pw * ramp * ramp * (3 - 2 * ramp)
        Q = P - off * (1 - f)[:, None]
        C[:, :6] = m.quantize(Q).view(np.uint8).reshape(-1, 6)
        w0 = np.ptp(P[sel & (t > 0.03), 0]); w1 = np.ptp(Q[sel & (t > 0.03), 0])
        print("LOD%d: %d shaft verts, width %.1f -> %.1f mm" % (c, sel.sum(), w0 * 1e3, w1 * 1e3))
    save_skin(m, src, dst)
    print("->", dst)


if __name__ == "__main__":
    main()
