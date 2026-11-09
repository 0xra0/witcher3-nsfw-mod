"""Replace the flat crotch floor of her LOD0 body mesh with a dense sculpted vulva.

  python3 -I tools/sculpt_vulva.py in.w2mesh out.w2mesh [preview.npz]
in.w2mesh: the ring-skinned body (skin_entrance.py output; its .1.buffer next to it).

The 16 floor triangles inside BOUND are dropped and refilled: a ~1.2 mm Delaunay grid over
the same outline (BOUND's vertices stay where they are, so nothing next to the patch
moves or cracks), displaced along the old surface normal into outer lips, inner lips, a
recessed groove, a clitoral hood and a mons swell, with an opening at the groove bottom
that runs as a closed tunnel up the canal (entrance_bones.CANAL). UVs, vertex colours and
the base skin come from the old surface under each point, so VfE's painted vulva still
lines up; the ring bones then take their share through entrance_bones.take(), so the
opening and the tunnel open with the existing animation. LOD1-3 are left as they are.
"""
import json, os, subprocess, sys, tempfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "work", "scratch", "bones")]
from mesh_geo import Mesh, dec_uv, enc_uv, dec_normals, enc_normals
import entrance_bones as eb

# Per body mesh: floor outline, interior floor verts, pelvis slot, first ring-bone slot (ring
# bones follow the mesh's own body bones). twa0_01 (Beauclair/courtesan naked torso) has the
# same crotch floor and UVs as twals_03, just its own vertex numbering and bone list.
TARGETS = {
    "twals_03_wa__body": ([3479, 3478, 3468, 3465, 3464, 3466, 3471, 3472, 3473, 3474, 3475, 3477],
                          [3476, 3467, 3469], 39, 81),
    "twa0_01_wa__body": ([1547, 1546, 1536, 1533, 1532, 1534, 1539, 1540, 1541, 1542, 1543, 1545],
                         [1544, 1535, 1537], 38, 79),
}
BOUND = INNER = PELVIS = RING0 = None         # set from TARGETS in main()
MM = 0.001
SCALE = float(os.environ.get("SCULPT_SCALE", "1"))   # overall relief strength
H = 1.2 * MM                                  # grid spacing
H_FINE, FINE_X, FINE_Y = 0.7 * MM, 6.5 * MM, (0.010, 0.080)
HOLE_Y, HOLE_A, HOLE_B, NR = 0.036, 2.2 * MM, 6.0 * MM, 20
TUNNEL_DEPTH, NT = 0.04, 8


def smooth(a, b, v):
    u = np.clip((v - a) / (b - a), 0, 1)
    return u * u * (3 - 2 * u)


def band(v, a0, a1, b1, b0):
    """1 on [a1, b1], smooth to 0 at a0 and b0."""
    return smooth(a0, a1, v) * (1 - smooth(b1, b0, v))


def height(x, y):
    """Outward displacement (m) of the floor at (x, y). Laid over VfE's painted vulva
    (mapped through the old UVs): opening y 0.028-0.036, inner lips a diamond up to the
    clitoris at y 0.074, outer lips y 0.010-0.085."""
    ax = np.abs(x)
    slit = band(y, 0.010, 0.020, 0.068, 0.078)
    xi = 1.6 * MM + 3.0 * MM * band(y, 0.038, 0.052, 0.058, 0.073)      # inner-lip line
    outer = 3.0 * np.exp(-((ax - 7.0 * MM) / (3.2 * MM)) ** 2) * band(y, 0.004, 0.014, 0.074, 0.088)
    groove = -3.5 * np.exp(-(x / (0.95 * xi)) ** 2) * slit
    inner = 1.5 * np.exp(-((ax - xi) / (0.8 * MM)) ** 2) * band(y, 0.028, 0.038, 0.068, 0.076)
    hood = 1.8 * np.exp(-(x ** 2 + ((y - 0.074) / 1.4) ** 2) / (2.6 * MM) ** 2)
    return (outer + groove + inner + hood) * MM * SCALE


CDT_PY = """
import json, sys
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt
d = json.load(open(sys.argv[-2]))
v, e, f, ov, oe, of = delaunay_2d_cdt([Vector(p) for p in d["pts"]], [tuple(x) for x in d["edges"]], [], 0, 1e-7)
assert len(v) == len(d["pts"]), "the constraints crossed"
remap = {i: o[0] for i, o in enumerate(ov)}
json.dump([[remap[i] for i in t] for t in f], open(sys.argv[-1], "w"))
"""


def cdt(pts, edges, work):
    """Constrained Delaunay triangulation (Blender's mathutils, run headless)."""
    with tempfile.TemporaryDirectory(dir=work) as t:
        i, o, py = (os.path.join(t, n) for n in ("in.json", "out.json", "cdt.py"))
        json.dump({"pts": np.asarray(pts).tolist(), "edges": [list(map(int, e)) for e in edges]}, open(i, "w"))
        open(py, "w").write(CDT_PY)
        r = subprocess.run(["blender", "-b", "--factory-startup", "--python", py, "--", i, o],
                           capture_output=True, text=True)
        if not os.path.exists(o):
            sys.exit("blender cdt failed:\n" + r.stdout[-2000:] + r.stderr[-2000:])
        return np.array(json.load(open(o)))


def in_poly(pts, poly):
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    for (x0, y0), (x1, y1) in zip(poly, np.roll(poly, -1, 0)):
        c = ((y0 > y) != (y1 > y)) & (x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-30) + x0)
        inside ^= c
    return inside


def seg_dist(pts, poly):
    d = np.full(len(pts), np.inf)
    for a, b in zip(poly, np.roll(poly, -1, 0)):
        ab = b - a
        t = np.clip(((pts - a) @ ab) / (ab @ ab), 0, 1)
        d = np.minimum(d, np.linalg.norm(pts - (a + t[:, None] * ab), axis=1))
    return d


class Base:
    """Piecewise-linear lookup over the old floor triangles in the (x, y) plane."""
    def __init__(self, P, tris, attrs):
        self.P, self.tris, self.attrs = P, np.array(tris), attrs

    def bary(self, q):
        out = []
        for p in q:
            best = None
            for t in self.tris:
                a, b, c = self.P[t, :2]
                m = np.array([b - a, c - a]).T
                l1, l2 = np.linalg.solve(m, p - a)
                w = np.array([1 - l1 - l2, l1, l2])
                if best is None or w.min() > best[1].min():
                    best = (t, w)
            out.append(best)
        return out

    def eval(self, q):
        res = {k: [] for k in self.attrs}
        for t, w in self.bary(q):
            w = np.clip(w, 0, None); w /= w.sum()
            for k, v in self.attrs.items():
                res[k].append(w @ v[t])
        return {k: np.array(v) for k, v in res.items()}


def pre_ring(coords):
    """[n,16] coords bytes -> [n, nb] weights with the ring bones folded back into pelvis."""
    W = np.zeros((len(coords), RING0 + 12))
    for i, row in enumerate(coords):
        for b, w in zip(row[8:12], row[12:16]):
            W[i, PELVIS if b >= RING0 else b] += w / 255.0
    return W / W.sum(1, keepdims=True)


def skin_bytes(wvec, q):
    names = {RING0 + k: n for k, n in enumerate(eb.ALL)}
    slot = {n: s for s, n in names.items()}
    w = {int(b): float(v) for b, v in enumerate(wvec) if v > 1e-4}
    w = eb.take(w, PELVIS, tuple(q))
    w = {slot.get(b, b): v for b, v in w.items()}
    s = sorted(((b, v) for b, v in w.items() if v > 1e-3), key=lambda t: -t[1])
    s = s[:4]
    tot = sum(v for _, v in s)
    qb = [int(round(255 * v / tot)) for _, v in s]
    qb[0] += 255 - sum(qb)
    return [b for b, _ in s] + [0] * (4 - len(s)), qb + [0] * (4 - len(s))


def main():
    global BOUND, INNER, PELVIS, RING0
    src, dst = sys.argv[1:3]
    BOUND, INNER, PELVIS, RING0 = TARGETS[os.path.basename(src).split(".")[0]]
    m = Mesh.load(src)
    ch = m.chunks[0]
    P = m.positions(0)
    uv = dec_uv(ch["uv"])
    nrm, ntop, tan, ttop = dec_normals(ch["normals"])
    I = ch["indices"].reshape(-1, 3)
    region = set(BOUND + INNER)
    drop = np.array([set(f.tolist()) <= region for f in I])
    assert drop.sum() == 16, drop.sum()
    old = I[drop]
    # winding: does (b-a)x(c-a) point along the stored normal?
    a, b, c = P[old[0]]
    ccw_out = np.cross(b - a, c - a) @ nrm[old[0]].sum(0) > 0
    poly = P[BOUND, :2]
    base = Base(P, old, {"z": P[:, 2], "uv": uv, "n": nrm, "vc": ch["vc"].astype(float),
                         "w": pre_ring(ch["coords"]), "t": tan})

    pts, th = floor_points(poly)
    nb, hole0 = len(poly), len(poly)
    cons = [(i, (i + 1) % nb) for i in range(nb)] + [(hole0 + k, hole0 + (k + 1) % NR) for k in range(NR)]
    tri = cdt(pts, cons, os.path.dirname(os.path.abspath(dst)))
    cen = pts[tri].mean(1)
    keep = in_poly(cen, poly) & (((cen[:, 0] / HOLE_A) ** 2 + ((cen[:, 1] - HOLE_Y) / HOLE_B) ** 2) > 1.0)
    keep &= ~np.all((tri >= hole0) & (tri < hole0 + NR), axis=1)
    tri = tri[keep]
    edges = {tuple(sorted(e)) for t in tri for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))}
    missing = [(i, (i + 1) % nb) for i in range(nb) if tuple(sorted((i, (i + 1) % nb))) not in edges]
    assert not missing, ("boundary edges lost by the triangulation", missing)

    # --- 3D surface ----------------------------------------------------------------
    newp = pts[nb:]
    B = base.eval(newp)
    nn = B["n"] / np.linalg.norm(B["n"], axis=1, keepdims=True)
    hgt = height(newp[:, 0], newp[:, 1])
    # fade to zero at the outline so the old neighbours meet the patch without a ridge
    hgt *= smooth(0.0, 4.0 * MM, seg_dist(newp, poly))
    surf = np.column_stack([newp, B["z"]]) + hgt[:, None] * nn
    # --- tunnel ----------------------------------------------------------------------
    canal = np.array(eb.CANAL)
    rim = surf[:NR]
    rim_c = rim.mean(0)
    rings, ruv = [], []
    uvc = base.eval(np.array([[0.0, HOLE_Y]]))["uv"][0]
    for j in range(1, NT + 1):
        t = j / NT
        shrink = 1 - 0.35 * smooth(0, 1, t)                     # narrow a little, then round
        off = rim - rim_c
        lat, fwd = off[:, 0], off @ np.array(eb.FRONT)
        circ = np.sqrt(HOLE_A * HOLE_B)
        lat2 = (1 - t) * lat + t * circ * np.cos(th)
        fwd2 = (1 - t) * fwd + t * circ * np.sin(th)
        c = rim_c + canal * TUNNEL_DEPTH * t
        rings.append(c + shrink * (lat2[:, None] * np.array(eb.SIDE) + fwd2[:, None] * np.array(eb.FRONT)))
        ruv.append(uvc + (B["uv"][:NR] - uvc) * (1 - 0.8 * t))
    cap = rim_c + canal * (TUNNEL_DEPTH + 2 * MM)
    tun = np.vstack(rings + [cap[None]])
    tun_uv = np.vstack(ruv + [uvc[None]])
    # --- assemble -------------------------------------------------------------------
    nv0 = len(P)
    # point index -> mesh vertex: boundary -> existing, the rest -> appended in order
    pm = np.concatenate([np.array(BOUND), nv0 + np.arange(len(newp))])
    ftri = pm[tri]
    allpos = np.vstack([P, surf, tun])
    nsurf = len(surf)
    tbase = nv0 + nsurf
    tt = []
    rim_idx = nv0 + np.arange(NR)
    prev = rim_idx
    for j in range(NT):
        cur = tbase + j * NR + np.arange(NR)
        for k in range(NR):
            a_, b_ = prev[k], prev[(k + 1) % NR]
            c_, d_ = cur[k], cur[(k + 1) % NR]
            tt += [(a_, b_, d_), (a_, d_, c_)]
        prev = cur
    capi = tbase + NT * NR
    tt += [(prev[k], prev[(k + 1) % NR], capi) for k in range(NR)]
    tt = np.array(tt)
    # orient: floor faces along the old normal, tunnel faces toward its axis
    def orient(F, want):
        a, b, c = allpos[F[:, 0]], allpos[F[:, 1]], allpos[F[:, 2]]
        cr = np.cross(b - a, c - a)
        flip = (np.einsum("ij,ij->i", cr, want) > 0) != ccw_out
        F = F.copy(); F[flip] = F[flip][:, [0, 2, 1]]
        return F
    tc = allpos[ftri].mean(1)
    ftri = orient(ftri, base.eval(tc[:, :2])["n"])
    cen3 = allpos[tt].mean(1)
    axis_pt = rim_c + np.outer((cen3 - rim_c) @ canal, canal)
    tt = orient(tt, axis_pt - cen3)
    newF = np.vstack([ftri, tt])
    nnew = nsurf + len(tun)
    # normals (area-weighted over the new faces; old outline vertices keep theirs)
    vn = np.zeros((len(allpos), 3))
    a, b, c = allpos[newF[:, 0]], allpos[newF[:, 1]], allpos[newF[:, 2]]
    fn = np.cross(b - a, c - a) * (1 if ccw_out else -1)
    for k in range(3):
        np.add.at(vn, newF[:, k], fn)
    vn = vn[nv0:]
    vn /= np.linalg.norm(vn, axis=1, keepdims=True)
    # tangents: the old surface's, made perpendicular to the new normal
    tb = np.vstack([B["t"], np.repeat(B["t"][:1], len(tun), 0)])
    tb -= np.einsum("ij,ij->i", tb, vn)[:, None] * vn
    tb /= np.linalg.norm(tb, axis=1, keepdims=True)
    # streams
    newpos = allpos[nv0:]
    coords = np.zeros((nnew, 16), np.uint8)
    coords[:, :6] = m.quantize(newpos).view(np.uint8).reshape(-1, 6)
    wv = np.vstack([B["w"], np.repeat(np.eye(B["w"].shape[1])[PELVIS][None], len(tun), 0)])
    for i in range(nnew):
        bi, bw = skin_bytes(wv[i], newpos[i])
        coords[i, 8:12], coords[i, 12:16] = bi, bw
    uvs = np.vstack([B["uv"], tun_uv])
    vc = np.vstack([B["vc"], np.repeat(base.eval(np.array([[0.0, HOLE_Y]]))["vc"], len(tun), 0)])
    ch["coords"] = np.vstack([ch["coords"], coords])
    ch["uv"] = np.vstack([ch["uv"], enc_uv(uvs)])
    ch["normals"] = np.vstack([ch["normals"], enc_normals(vn, np.ones(nnew, int), tb, np.zeros(nnew, int))])
    ch["vc"] = np.vstack([ch["vc"], np.clip(np.round(vc), 0, 255).astype(np.uint8)])
    ch["indices"] = np.concatenate([I[~drop].ravel(), newF.ravel()]).astype("<u2")
    m.save(dst)
    ring_w = sum(1 for r in coords if any(b >= RING0 for b, w in zip(r[8:12], r[12:16]) if w))
    print("patch: %d floor + %d tunnel verts, %d + %d tris (dropped 16); %d verts on ring bones; height %.1f..%.1f mm"
          % (nsurf, len(tun), len(ftri), len(tt), ring_w, hgt.min() / MM, hgt.max() / MM))
    print("LOD0 now", len(ch["coords"]), "verts", len(ch["indices"]) // 3, "tris ->", dst)
    if len(sys.argv) > 3:
        np.savez(sys.argv[3], pos=allpos, F=np.vstack([I[~drop], newF]), new=np.arange(nv0, len(allpos)), newF=newF)


def floor_points(poly):
    """The patch's 2D points (x, y) in rest space: the outline, the hole's two rings, then
    the grid. Vertex RETAIL_N + k of the output mesh is point len(poly) + k (sculpt_mons.py
    relies on this to get each sculpt vertex's exact grid position back)."""
    xs = np.arange(poly[:, 0].min(), poly[:, 0].max() + H, H)
    ys = np.arange(poly[:, 1].min(), poly[:, 1].max() + H, H)
    g = np.array([(x + (H / 2 if j % 2 else 0), y) for j, y in enumerate(ys) for x in xs])
    # finer grid along the slit, where the groove walls are steep
    fine = lambda q: (np.abs(q[:, 0]) < FINE_X) & (q[:, 1] > FINE_Y[0]) & (q[:, 1] < FINE_Y[1])
    xf = np.arange(-FINE_X, FINE_X + H_FINE, H_FINE)
    yf = np.arange(FINE_Y[0], FINE_Y[1], H_FINE)
    gf = np.array([(x + (H_FINE / 2 if j % 2 else 0), y) for j, y in enumerate(yf) for x in xf])
    g = np.vstack([g[~fine(g)], gf[fine(gf)]])
    g = g[in_poly(g, poly) & (seg_dist(g, poly) > 0.55 * H)]
    e = ((g[:, 0] / HOLE_A) ** 2 + ((g[:, 1] - HOLE_Y) / HOLE_B) ** 2)
    g = g[e > 1.6]
    th = np.linspace(0, 2 * np.pi, NR, endpoint=False)
    ring = np.stack([HOLE_A * np.cos(th), HOLE_Y + HOLE_B * np.sin(th)], 1)
    # one intermediate ring keeps the slope round the hole smooth
    ring2 = np.stack([1.25 * HOLE_A * np.cos(th + np.pi / NR), HOLE_Y + 1.2 * HOLE_B * np.sin(th + np.pi / NR)], 1)
    return np.vstack([poly, ring, ring2, g]), th



if __name__ == "__main__":
    main()
