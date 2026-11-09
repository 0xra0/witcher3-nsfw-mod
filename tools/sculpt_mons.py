"""Carry the vulva cleft from the crotch floor up onto the front of her mons (v39).

  python3 -I tools/sculpt_mons.py cur.w2mesh retail.w2mesh info.json out.w2mesh [preview.npz]
cur.w2mesh: the live sculpted torso (v38: reskin_ring.py output). retail.w2mesh: the same
mesh before sculpt_vulva (twa0/ring), whose 16 floor triangles give the flat base surface.

The close-up camera looks at her from front-above (dir ~(0,-0.72,-0.70) in rest space), so
the floor sculpt (normals pointing down) faces away and only the retail mons front shows:
plain low-poly skin, the shaft vanishing under it. Here the front half of the floor sculpt
(UV v < VCUT) and the retail mons faces in MONS are dropped and refilled as one dense patch.
It is triangulated in an unrolled plane (x, y): floor points keep sculpt_vulva's exact grid
position, and the mons is folded down onto the floor plane about its front edge (stored
UVs are half floats, ~1 mm apart here, too coarse to triangulate in). Its relief is sculpt_vulva's design with the lips, groove and hood
moved forward round the bend: the outer lips part around the groove at the floor's front
edge and close into the anterior commissure ~3 cm up the mons. The cleft's UVs are pulled
onto the painted hood/upper slit, so the texture follows the new shape. Outline vertices
keep every byte, and the relief fades to the old surface 4 mm inside the outline, so
nothing outside the patch moves. Skin is the old surface's, interpolated. LOD1-3 are left
as they are.
"""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "work", "scratch", "bones")]
from mesh_geo import Mesh, dec_uv, enc_uv, dec_normals, enc_normals
import entrance_bones as eb
from sculpt_vulva import TARGETS, cdt, in_poly, seg_dist, smooth, band, floor_points
from crotch_pelvis import RETAIL_N, named
from seam_lock import pack

MM = 0.001
SCALE = float(os.environ.get("SCULPT_SCALE", "2.5"))  # same as the shipped floor sculpt
MONS = [1534, 1539, 1540, 1538, 1242, 1240, 1244, 1227, 1229]
VCUT = 0.955                 # floor sculpt triangles in front of this UV v are redone
# the cleft UV pull onto the painted slit: full inside |x| < X0, gone past X1; ends between y Y0 and Y1
UV_X0, UV_X1, UV_Y0, UV_Y1 = (float(v) for v in os.environ.get("UV_PULL", "0.007,0.011,0.122,0.132").split(","))
EDGE = [1534, 1539, 1540]    # the floor's front edge, where the mons is unrolled from
H, H_FINE = 1.1 * MM, 0.7 * MM   # grid spacing (fine along the cleft)
FINE_X = 9.0 * MM
FADE = 4.0 * MM              # relief fades to the old surface over this distance from the outline
FADE_BASE = 12.0 * MM        # ... and the smooth (Phong) base over this one
# Interpolating the retail mons skin mixes up to 7 bones; dropping the smallest to fit the
# game's 4 jumps wherever the dropped bone changes (a 2-3 % thigh share is ~2 mm at frame
# 300). The roll bones only twist the thigh, so fit4() folds them into it, the same way for
# every vertex (per-vertex choices ripple). Fading the fold in from the outline was tried:
# where left and right legs meet (vertex 1227) that leaves 6 bones and limit() truncates.
ROLL2 = {"l_legRoll2": "l_legRoll", "r_legRoll2": "r_legRoll"}
ROLL = {"l_legRoll": "l_thigh", "r_legRoll": "r_thigh"}
N_TUNNEL = 161               # sculpt_vulva's tunnel verts, last in the vertex list


def height(x, y):
    """Outward displacement (m) at lateral x (m) and unrolled length y (m): y is the floor y
    up to the front edge (0.089) and continues as arc length up the mons. Same terms as
    sculpt_vulva.height(), identical for y < 0.058; forward of that the lips stay parted over
    the bend and meet at the commissure (y ~0.12)."""
    ax = np.abs(x)
    slit = band(y, 0.010, 0.020, 0.098, 0.118)
    # lips stay parted from the entrance up to the bend (v39 closed them at 0.073 and parted
    # them again at the bend: an opening the camera saw ~4 cm in front of the shaft)
    xi = 1.6 * MM + 3.0 * MM * band(y, 0.038, 0.052, 0.088, 0.106)
    xo = 7.0 * MM - 2.5 * MM * smooth(0.092, 0.115, y)                  # outer lips close up the mons
    soft = smooth(0.068, 0.090, y)                                    # rounder, lower lips round the bend
    outer = ((3.0 - 0.9 * soft) * np.exp(-((ax - xo) / ((3.2 + 1.2 * soft) * MM)) ** 2)
             * band(y, 0.004, 0.014, 0.095, 0.118))
    groove = -3.5 * np.exp(-(x / (0.95 * xi)) ** 2) * slit
    inner = 1.5 * np.exp(-((ax - xi) / (0.8 * MM)) ** 2) * band(y, 0.028, 0.038, 0.088, 0.100)
    hood = 1.8 * np.exp(-(x ** 2 + ((y - 0.096) / 1.4) ** 2) / (2.6 * MM) ** 2)
    return (outer + groove + inner + hood) * MM * SCALE


def bary_eval(q, Q, tris, attrs):
    """Piecewise-linear lookup of attrs (per vertex) at 2D points q over triangles tris of
    the 2D vertex layout Q; each point takes the triangle it is most inside of."""
    a, b, c = Q[tris[:, 0]], Q[tris[:, 1]], Q[tris[:, 2]]
    e1, e2 = b - a, c - a
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    out = {k: [] for k in attrs}
    for s in range(0, len(q), 256):
        p = q[s:s + 256, None, :] - a[None]
        l1 = (p[..., 0] * e2[:, 1] - p[..., 1] * e2[:, 0]) / det
        l2 = (e1[:, 0] * p[..., 1] - e1[:, 1] * p[..., 0]) / det
        w = np.stack([1 - l1 - l2, l1, l2], -1)
        best = w.min(-1).argmax(1)
        wb = np.clip(w[np.arange(len(best)), best], 0, None)
        wb /= wb.sum(1, keepdims=True)
        t = tris[best]
        for k, v in attrs.items():
            out[k].append(np.einsum("ij,ij...->i...", wb, v[t]))
        out.setdefault("_tri", []).append(best)
        out.setdefault("_w", []).append(wb)
    return {k: np.concatenate(v) for k, v in out.items()}


def phong(tris, w, p, n, alpha=0.75):
    """Phong tessellation: the point at barycentric w on each triangle, bulged so the
    surface follows the vertex normals instead of the flat triangle (crease-free base)."""
    P3, N3 = p[tris], n[tris]
    L = np.einsum("ij,ijk->ik", w, P3)
    proj = L[:, None] - np.einsum("ijk,ijk->ij", L[:, None] - P3, N3)[..., None] * N3
    return (1 - alpha) * L + alpha * np.einsum("ij,ijk->ik", w, proj)


def fit4(w, g=1.0):
    """Skin {bone: w} -> at most 4 bones: roll bones folded as above (g = share folded),
    anything left over goes through entrance_bones.limit (rest pose kept). Also returns the
    share limit() had to move."""
    out = {}
    for b, v in w.items():
        b = ROLL2.get(b, b)
        if b in ROLL:
            out[ROLL[b]] = out.get(ROLL[b], 0.0) + g * v
            v *= 1 - g
        out[b] = out.get(b, 0.0) + v
    out = {b: v for b, v in out.items() if v > 1e-3}
    return eb.limit(out, "pelvis"), sum(sorted(out.values())[:-4])


def unroll(p, P):
    """Rest position of a mons vertex -> (x, y) in the floor plane: x as is, y = the front
    edge's y at that x plus the distance to the edge across (y, z)."""
    ex = P[EDGE, 0]
    o = np.argsort(ex)
    e = np.array([np.interp(p[0], ex[o], P[EDGE, k][o]) for k in range(3)])
    return np.array([p[0], e[1] + np.hypot(p[1] - e[1], p[2] - e[2])])


def loop(edges):
    """Boundary edges (each used by one region triangle, kept in its winding) -> one ordered
    vertex loop."""
    nxt = {}
    for a, b in edges:
        assert a not in nxt, ("outline touches itself at", a)
        nxt[a] = b
    start = next(iter(nxt))
    out, v = [start], nxt[start]
    while v != start:
        out.append(v)
        v = nxt[v]
    assert len(out) == len(nxt), "outline is more than one loop"
    return out


def main():
    src, ret, info, dst = sys.argv[1:5]
    BOUND, INNER, PELVIS, RING0 = TARGETS["twa0_01_wa__body"]
    names = json.load(open(info))["bones"] + eb.ALL
    slot = {n: i for i, n in enumerate(names)}
    m, r = Mesh.load(src), Mesh.load(ret)
    ch = m.chunks[0]
    P = m.positions(0)
    uv = dec_uv(ch["uv"])
    nrm, _, tan, _ = dec_normals(ch["normals"])
    I = ch["indices"].reshape(-1, 3)
    nv0 = len(P)
    assert np.allclose(r.positions(0)[:RETAIL_N], P[:RETAIL_N], atol=1e-5)

    # --- region -----------------------------------------------------------------------
    sculpt_surf = set(range(RETAIL_N, nv0 - N_TUNNEL))
    floor_ok = set(BOUND) | sculpt_surf
    mons = set(MONS)
    in_floor = np.array([set(t.tolist()) <= floor_ok and uv[t, 1].max() < VCUT for t in I])
    in_mons = np.array([set(t.tolist()) <= mons for t in I])
    reg = in_floor | in_mons
    RT = I[reg]
    cnt = {}
    for t in RT:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            cnt[(a, b)] = cnt.get((a, b), 0) + 1
    bedges = [(a, b) for (a, b) in cnt if (b, a) not in cnt]
    out_ids = loop(bedges)
    interior = set(RT.ravel().tolist()) - set(out_ids)
    others = I[~reg]
    assert not (set(others.ravel().tolist()) & interior), "an interior vertex is used outside the patch"
    for v in interior:
        if v < RETAIL_N:   # a retail vertex the patch moves must not have a UV-seam twin
            twin = np.where(np.linalg.norm(P - P[v], axis=1) < 1e-5)[0]
            assert list(twin) == [v], ("retail vertex has a twin", v, twin)
    print("region: %d floor + %d mons tris, outline %d verts, %d interior dropped"
          % (in_floor.sum(), in_mons.sum(), len(out_ids), len(interior)))

    # --- unrolled plane -------------------------------------------------------------------
    Q = np.full((nv0, 2), np.nan)
    fpts = floor_points(P[BOUND, :2])[0]
    nb0 = len(BOUND)
    assert len(fpts) - nb0 == nv0 - N_TUNNEL - RETAIL_N, "sculpt grid does not match the mesh"
    Q[RETAIL_N:nv0 - N_TUNNEL] = fpts[nb0:]
    Q[BOUND + INNER] = P[BOUND + INNER, :2]
    for v in set(MONS) - set(BOUND):
        Q[v] = unroll(P[v], P)
    assert not np.isnan(Q[RT]).any()
    a2, b2, c2 = Q[RT[:, 0]], Q[RT[:, 1]], Q[RT[:, 2]]
    sgn = np.sign((b2 - a2)[:, 0] * (c2 - a2)[:, 1] - (b2 - a2)[:, 1] * (c2 - a2)[:, 0])
    assert abs(sgn.sum()) == len(RT), "the unrolled region folds"
    poly = Q[out_ids]
    lo, hi = poly.min(0), poly.max(0)
    def grid(h, lo, hi):
        xs, ys = np.arange(lo[0], hi[0] + h, h), np.arange(lo[1], hi[1] + h, h)
        return np.array([(x + (h / 2 if j % 2 else 0), y) for j, y in enumerate(ys) for x in xs])
    g = grid(H, lo, hi)
    fine = lambda p: np.abs(p[:, 0]) < FINE_X
    gf = grid(H_FINE, np.array([-FINE_X, lo[1]]), np.array([FINE_X, hi[1]]))
    g = np.vstack([g[~fine(g)], gf[fine(gf)]])
    g = g[in_poly(g, poly) & (seg_dist(g, poly) > 0.55 * H)]
    pts = np.vstack([poly, g])
    nb = len(poly)
    tri = cdt(pts, [(i, (i + 1) % nb) for i in range(nb)], os.path.dirname(os.path.abspath(dst)))
    tri = tri[in_poly(pts[tri].mean(1), poly)]
    have = {tuple(sorted(e)) for t in tri for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))}
    lost = [i for i in range(nb) if tuple(sorted((i, (i + 1) % nb))) not in have]
    assert not lost, ("outline edges lost by the triangulation", lost)

    # --- old surface (cur) and flat base (retail) under every new point ---------------------
    newq = pts[nb:]
    print("cdt: %d pts %d tris" % (len(pts), len(tri)), flush=True)
    wdense = np.zeros((nv0, len(names)))
    for i in set(RT.ravel().tolist()):
        for n, v in named(ch["coords"][i], names).items():
            wdense[i, slot[n]] += v
    C = bary_eval(newq, Q, RT, {"p": P, "n": nrm, "t": tan, "vc": ch["vc"].astype(float), "w": wdense, "uv": uv})
    rI = r.chunks[0]["indices"].reshape(-1, 3)
    rfloor = rI[np.array([set(t.tolist()) <= set(BOUND + INNER) for t in rI])]
    assert len(rfloor) == 16
    rnrm = dec_normals(r.chunks[0]["normals"])[0]
    base_tris = np.vstack([rfloor, I[in_mons]])
    B = bary_eval(newq, Q, base_tris, {"p": r.positions(0), "n": rnrm})
    Bn = B["n"] / np.linalg.norm(B["n"], axis=1, keepdims=True)
    # the retail mons is a few big triangles drawn smooth: build on the smooth surface they
    # stand for, or the lips fold along their edges. The floor stays linear like the old sculpt.
    on_mons = B["_tri"] >= len(rfloor)
    rn = rnrm / np.linalg.norm(rnrm, axis=1, keepdims=True)
    fb = smooth(0.0, FADE_BASE, seg_dist(newq, poly))[on_mons, None]
    B["p"][on_mons] += fb * (phong(base_tris[B["_tri"][on_mons]], B["_w"][on_mons], r.positions(0), rn) - B["p"][on_mons])

    x, y = newq[:, 0], newq[:, 1]
    hgt = height(x, y)
    f = smooth(0.0, FADE, seg_dist(newq, poly))
    surf = C["p"] + f[:, None] * (B["p"] + hgt[:, None] * Bn - C["p"])

    # --- UVs: pull the cleft onto the painted hood/upper slit ------------------------------
    nuv = C["uv"].copy()
    ypt0, ypt1, vp0, vp1 = 0.060, 0.120, 0.955, 0.940
    v_paint = vp0 + (vp1 - vp0) * np.clip((y - ypt0) / (ypt1 - ypt0), 0, 1)
    wt = f * (1 - smooth(UV_X0, UV_X1, np.abs(x))) * smooth(ypt0, ypt0 + 0.006, y) * (1 - smooth(UV_Y0, UV_Y1, y))
    nuv[:, 1] += wt * (v_paint - nuv[:, 1])

    # --- assemble ------------------------------------------------------------------------
    pm = np.concatenate([np.array(out_ids), nv0 + np.arange(len(newq))])
    F = pm[tri]
    allpos = np.vstack([P, surf])
    a0, b0, c0 = P[RT[0]]
    ccw_out = np.cross(b0 - a0, c0 - a0) @ nrm[RT[0]].sum(0) > 0
    cr = np.cross(allpos[F[:, 1]] - allpos[F[:, 0]], allpos[F[:, 2]] - allpos[F[:, 0]])
    want = bary_eval(pts[tri].mean(1), Q, RT, {"n": nrm})["n"]
    flip = (np.einsum("ij,ij->i", cr, want) > 0) != ccw_out
    F[flip] = F[flip][:, [0, 2, 1]]
    vn = np.zeros((len(allpos), 3))
    fn = np.cross(allpos[F[:, 1]] - allpos[F[:, 0]], allpos[F[:, 2]] - allpos[F[:, 0]]) * (1 if ccw_out else -1)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    vn = vn[nv0:] / np.linalg.norm(vn[nv0:], axis=1, keepdims=True)
    # geometric normals inside; at the outline the old interpolated ones, so the patch
    # shades on into the triangles round it
    cn = C["n"] / np.linalg.norm(C["n"], axis=1, keepdims=True)
    vn = vn + (1 - f)[:, None] * (cn - vn)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True)
    tb = C["t"] - np.einsum("ij,ij->i", C["t"], vn)[:, None] * vn
    tb /= np.linalg.norm(tb, axis=1, keepdims=True)
    nnew = len(newq)
    coords = np.zeros((nnew, 16), np.uint8)
    coords[:, :6] = m.quantize(surf).view(np.uint8).reshape(-1, 6)
    # skin: the old surface's, interpolated, so the patch moves exactly with what is round it
    # (re-taking the ring share from position made it deform apart from the retail mons)
    ring_w, dropped = 0, 0.0
    for i in range(nnew):
        w = {names[b]: v for b, v in enumerate(C["w"][i]) if v > 1e-4}
        w, d = fit4(w)
        dropped = max(dropped, d)
        bn, bw = pack(w)
        coords[i, 8:12] = [slot[n] if v else 0 for n, v in zip(bn, bw)]
        coords[i, 12:16] = bw
        ring_w += any(n in eb.ALL for n, v in zip(bn, bw) if v)
    ch["coords"] = np.vstack([ch["coords"], coords])
    ch["uv"] = np.vstack([ch["uv"], enc_uv(nuv)])
    ch["normals"] = np.vstack([ch["normals"], enc_normals(vn, np.ones(nnew, int), tb, np.zeros(nnew, int))])
    ch["vc"] = np.vstack([ch["vc"], np.clip(np.round(C["vc"]), 0, 255).astype(np.uint8)])
    ch["indices"] = np.concatenate([I[~reg].ravel(), F.ravel()]).astype("<u2")
    m.save(dst)
    disp = np.linalg.norm(surf - C["p"], axis=1)
    print("patch: %d verts, %d tris (dropped %d); %d on ring bones, skin share past 4 bones %.4f; "
          "relief %.1f..%.1f mm; moved max %.1f mm; uv warped %d"
          % (nnew, len(F), reg.sum(), ring_w, dropped, hgt.min() / MM, hgt.max() / MM, disp.max() / MM, (wt > 0.05).sum()))
    print("LOD0 now", len(ch["coords"]), "verts", len(ch["indices"]) // 3, "tris ->", dst)
    if len(sys.argv) > 5:
        np.savez(sys.argv[5], pos=allpos, F=F, new=np.arange(nv0, len(allpos)), y=y, x=x)


if __name__ == "__main__":
    main()
