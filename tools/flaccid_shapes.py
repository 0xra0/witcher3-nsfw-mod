"""Blend shapes for TW3SE's w3.deform: Geralt's erect GeraltX shaft bent down to softer levels.

  python3 tools/flaccid_shapes.py l_01_mg__body.w2mesh out.twdf [preview.npz]

A mesh without penis bones (GeraltX's own l_01a_mg__body_underwear, the legs the game draws when
Geralt is undressed) takes the shaft weight from the nearest vertex of WEIGHTS_FROM=<mesh with them>.

The mesh is sculpted erect, so "erect" is the mesh itself (level 100) and each shape is the offset
to one softer level (lvl00 flaccid, lvl25, lvl50, lvl75). A straight blend from erect to flaccid
would pull the shaft through the scrotum on the way, so the Lua side crossfades between neighbouring
levels instead. Each level is a bend deformer along the shaft axis: the shaft is shortened and
thinned, then curved downward with constant curvature over its first part, so it arcs forward
over the scrotum before it hangs (the scrotum's front is at y 0.095, level with the shaft root).
"""
import os, struct, sys
import numpy as np
sys.path[:0] = [__file__.rsplit("/", 1)[0], __file__.rsplit("/", 2)[0] + "/work/scratch/bones"]
from mesh_geo import Mesh, dec_normals
from meshbones import parse_tail

BASE = np.array([0, 0.095, 0.945])                  # chain.json: shaft root and tip, model space
TIP = np.array([0, 0.240, 1.012])
LEVELS = (0, 25, 50, 75)

# level -> (bend angle in degrees, length scale, girth scale, bend radius in metres)
def level_params(level):
    soft = 1 - level / 100
    return 116 * soft, 1 - 0.3 * soft, 1 - 0.2 * soft, 0.034


def bend(p, n, pw, level):
    """Positions and normals of the penis vertices at one level (rest of the mesh unchanged)."""
    angle, ls, gs, R = level_params(level)
    L = np.linalg.norm(TIP - BASE)
    a = (TIP - BASE) / L
    phi0 = np.arctan2(a[2], a[1])                       # shaft pitch above horizontal
    q = p - BASE
    s = q @ a
    e1 = np.array([0, -np.sin(phi0), np.cos(phi0)])    # "up" across the shaft
    c1 = q @ e1
    cx = q[:, 0]
    # root stays on the body: girth and length change ramp in over the first 2.5 cm
    ramp = np.clip(s / 0.025, 0, 1)
    ramp = ramp * ramp * (3 - 2 * ramp)
    g = 1 + (gs - 1) * ramp
    u = np.where(s > 0, s * ls, s)                      # arc length along the new centreline
    th = np.radians(angle)
    A = R * th                                          # arc length of the bend
    k = th / A if th > 1e-6 else 0.0
    ub = np.clip(u, 0, A)
    alpha = k * ub                                      # how far each section has turned
    phi = phi0 - alpha
    if k:
        y = (np.sin(phi0) - np.sin(phi)) / k
        z = (np.cos(phi) - np.cos(phi0)) / k
    else:
        y, z = ub * np.cos(phi0), ub * np.sin(phi0)
    rest = u - ub                                       # straight part after the arc (and s < 0)
    y = y + rest * np.cos(phi)
    z = z + rest * np.sin(phi)
    t_e1 = np.stack([np.zeros_like(phi), -np.sin(phi), np.cos(phi)], 1)
    out = BASE + np.stack([cx * g, y, z], 1) + (c1 * g)[:, None] * t_e1
    # normals turn with their section (rotation about x by -alpha)
    ca, sa = np.cos(-alpha), np.sin(-alpha)
    nn = np.stack([n[:, 0], ca * n[:, 1] - sa * n[:, 2], sa * n[:, 1] + ca * n[:, 2]], 1)
    # vertices only partly on the chain (round the root) move by their chain weight
    w = pw[:, None]
    return p + w * (out - p), n + w * (nn - n)


def penis_weight(m):
    c = m.c
    e = next(e for e in c.exports if c.names[e[0]] == "CMesh")
    _, endp = c.props(e[4] + 1, e[4] + e[3])
    names = [c.names[i] for i in parse_tail(c.d, endp)["names"]]
    pen = [i for i, s in enumerate(names) if s.startswith("penis")]
    assert len(pen) == 4, names
    ch = m.chunks[0]
    b = ch["coords"][:, 8:12]
    w = ch["coords"][:, 12:16].astype(float) / 255
    return sum(((b == i) * w).sum(1) for i in pen)


def write_twdf(path, names, chunk_deltas, chunk_ndeltas):
    """TWDF v2 with normal offsets: {chunk: (K, n, 3)} for both."""
    out = bytearray(b"TWDF" + struct.pack("<III", 2, len(names), len(chunk_deltas)) + struct.pack("<I", 1))
    for s in names:
        b = s.encode()
        out += struct.pack("<H", len(b)) + b
    for ci in sorted(chunk_deltas):
        d, nd = chunk_deltas[ci], chunk_ndeltas[ci]
        out += struct.pack("<II", ci, d.shape[1])
        out += np.asarray(d, "<f4").tobytes() + np.asarray(nd, "<f4").tobytes()
    open(path, "wb").write(bytes(out))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    m = Mesh.load(src)
    assert len(m.chunks) == 1, "one chunk expected (GeraltX legs mesh)"
    p = m.positions(0)
    n = dec_normals(m.chunks[0]["normals"])[0]
    if os.environ.get("WEIGHTS_FROM"):
        from scipy.spatial import cKDTree
        w = Mesh.load(os.environ["WEIGHTS_FROM"])
        d, i = cKDTree(w.positions(0)).query(p)
        pw = penis_weight(w)[i]
        print("weights from", os.environ["WEIGHTS_FROM"], "nearest max %.4f m" % d.max())
    else:
        pw = penis_weight(m)
    sel = pw > 0
    names, D, ND, prev = [], [], [], {}
    for lv in LEVELS:
        P, N = p.copy(), n.copy()
        P[sel], N[sel] = bend(p[sel], n[sel], pw[sel], lv)
        names.append("lvl%02d" % lv)
        D.append(P - p); ND.append(N - n)
        prev["lvl%02d" % lv] = P
        print("lvl%02d max offset %.3f m" % (lv, np.linalg.norm(P - p, axis=1).max()))
    write_twdf(dst, names, {0: np.array(D)}, {0: np.array(ND)})
    print("wrote", dst, "shapes", names, "vertices", len(p), "moved", int(sel.sum()))
    # check.lua beside it: sample vertices the Lua side compares with w3.deform.dump's output,
    # so a mesh whose vertex order differs from this file is never deformed
    idx = list(np.flatnonzero(sel)[::997]) + list(np.flatnonzero(~sel)[::1999])
    rows = ",\n".join("  {%d, %.5f, %.5f, %.5f}" % (i, *p[i]) for i in idx)
    open(dst.rsplit("/", 1)[0] + "/check.lua", "w").write(
        "-- written by tools/flaccid_shapes.py: vertex count and samples {index (from 0), x, y, z}\n"
        "return {count = %d, samples = {\n%s\n}}\n" % (len(p), rows))
    if len(sys.argv) > 3:
        np.savez(sys.argv[3], base=p, faces=m.chunks[0]["indices"].reshape(-1, 3), pw=pw, **prev)


if __name__ == "__main__":
    main()
