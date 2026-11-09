"""Replace the stored LOD0 normals of chosen vertices in a cooked w2mesh.

  python3 -I tools/set_normals.py in.w2mesh normals.json out.w2mesh

normals.json: {"verts": [i, ...], "normals": [[x, y, z], ...]} in mesh space (e.g. from
work/scratch/v46/crease_n.py). Each tangent is re-orthogonalised to its new normal; the
top bits, positions, skin and every other chunk keep their bytes.
"""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "work", "scratch", "bones")]
from mesh_geo import Mesh, dec_normals, enc_normals


def main():
    src, js, dst = sys.argv[1:4]
    m = Mesh.load(src)
    ch = m.chunks[0]
    n, nt, t, tt = dec_normals(ch["normals"])
    d = json.load(open(js))
    vi, nn = np.array(d["verts"]), np.array(d["normals"], float)
    nn /= np.linalg.norm(nn, axis=1, keepdims=True)
    tv = t[vi] - (t[vi] * nn).sum(1, keepdims=True) * nn
    n, t = n.copy(), t.copy()
    n[vi], t[vi] = nn, tv / np.maximum(np.linalg.norm(tv, axis=1, keepdims=True), 1e-9)
    ch["normals"] = enc_normals(n, nt, t, tt)
    m.save(dst)
    print("set %d normals -> %s" % (len(vi), dst))


if __name__ == "__main__":
    main()
