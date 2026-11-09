"""Redo the ring-bone skin of the vulva sculpt from the skin it has now.

  python3 -I tools/reskin_ring.py torso.w2mesh torso.info.json out.w2mesh

entrance_bones.take() gives the ring bones a share of each vertex's PELVIS weight. The
sculpt's ring weights were taken when its floor was still ~60% thigh, so they scale with
that old pelvis share, which varied a lot between neighbours; crotch_pelvis.py later moved
the thigh share to the pelvis but left the ring weights as they were. Opening the ring then
moved neighbouring vertices by different amounts and folded the grid (the reason v36 had to
set open_scale 0). Here every LOD0 sculpt vertex (index >= RETAIL_N) has its vag_/vagl_
weight folded back into the pelvis and take() run again, so the ring share is the designed
radial profile of position alone. Retail and leg skin are not touched.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "work", "scratch", "bones")]
from mesh_geo import Mesh
import entrance_bones as eb
from crotch_pelvis import RETAIL_N, named, save_skin
from seam_lock import pack


def main():
    src, info, dst = sys.argv[1:4]
    names = json.load(open(info))["bones"] + eb.ALL
    idx = {n: i for i, n in enumerate(names)}
    m = Mesh.load(src)
    ch = m.chunks[0]
    P = m.positions(0)
    before = after = 0.0
    for i in range(RETAIL_N, len(P)):
        w = named(ch["coords"][i], names)
        ringw = sum(v for n, v in w.items() if n in eb.ALL)
        before += ringw
        w = {n: v for n, v in w.items() if n not in eb.ALL}
        w["pelvis"] = w.get("pelvis", 0.0) + ringw
        w = eb.take(w, "pelvis", tuple(P[i]))
        after += sum(v for n, v in w.items() if n in eb.ALL)
        bn, bw = pack(w)
        ch["coords"][i][8:12] = [idx[n] if v else 0 for n, v in zip(bn, bw)]
        ch["coords"][i][12:16] = bw
    n = len(P) - RETAIL_N
    print("LOD0: %d sculpt verts, mean ring share %.3f -> %.3f" % (n, before / n, after / n))
    save_skin(m, src, dst)
    print("->", dst)


if __name__ == "__main__":
    main()
