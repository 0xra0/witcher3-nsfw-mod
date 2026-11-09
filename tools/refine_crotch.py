"""Round off the coarse retail crotch around the sculpt: subdivide torso AND legs together.

  python3 -I tools/refine_crotch.py torso.w2mesh torso.info.json legs.w2mesh legs.info.json \
      out_torso.w2mesh out_legs.w2mesh [radius levels]

sculpt_vulva.py rebuilt only the 2 cm floor strip. Round it the retail LOD0 is ~2 cm
triangles (the mound and the inner thighs, split between twa0_01 and the ls_02 leg piece);
in the cowgirl squat seen from below they read as flat sliced panels with sharp folds
beside the shaft. Every LOD0 triangle whose centre lies within `radius` of E0 (default
7 cm; retail triangles only, the sculpt is left alone) is split 1-to-4 `levels` times
(default 2). An edge is split only if every triangle on it, in either mesh, is in the
region, so nothing outside gains a T-junction; region triangles with unsplit edges take the
usual 2- or 3-way split. New points sit on the PN-triangle (cubic point-normal) curve of
their edge, so the facets bulge into the smooth surface their vertex normals describe.
Points are keyed by position over both meshes (UV seams, the torso/leg weld), so every copy
of an edge gets the same point and the same skin and the weld stays closed. Normals inside
the region are recomputed over both meshes' faces; region-boundary vertices keep theirs.
"""
import json, os, sys
from collections import defaultdict
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "work", "scratch", "bones")]
from mesh_geo import Mesh, dec_uv, enc_uv, dec_normals, enc_normals
import entrance_bones as eb
from seam_lock import pack

Q = 1e-4    # position key grid (m): the torso/leg weld matches to < 5e-4


def key(p):
    return tuple(np.round(np.asarray(p) / Q).astype(int))


class Part:
    """One mesh's LOD0 as editable lists."""

    def __init__(self, path, names, retail_n=None):
        self.m = m = Mesh.load(path)
        ch = m.chunks[0]
        self.names = names
        self.P = list(m.positions(0))
        n, nt, t, tt = dec_normals(ch["normals"])
        self.N, self.NT, self.T, self.TT = list(n), list(nt), list(t), list(tt)
        self.UV = list(dec_uv(ch["uv"]))
        self.VC = list(ch["vc"].astype(float)) if "vc" not in m.absent else None
        self.W = [self.weights(r) for r in ch["coords"]]
        self.F = [list(f) for f in ch["indices"].reshape(-1, 3)]
        self.nv0 = len(self.P)
        self.retail_n = retail_n or self.nv0

    def weights(self, row):
        w = defaultdict(float)
        for b, v in zip(row[8:12], row[12:16]):
            if v:
                w[self.names[int(b)]] += v / 255.0
        return dict(w)

    def add(self, p, n, t, tt, uv, vc, w):
        self.P.append(p); self.N.append(n); self.NT.append(1); self.T.append(t); self.TT.append(tt)
        self.UV.append(uv); self.W.append(w)
        if self.VC is not None:
            self.VC.append(vc)
        return len(self.P) - 1


def pn_mid(p0, p1, n0, n1):
    """Midpoint and normal of the PN-triangle edge curve between (p0,n0) and (p1,n1)."""
    d = p1 - p0
    off = ((d @ n0) * n0 - (d @ n1) * n1) / 8
    L = np.linalg.norm(d)
    if np.linalg.norm(off) > 0.25 * L:          # a fold the normals can't describe: cap it
        off *= 0.25 * L / np.linalg.norm(off)
    mid = (p0 + p1) / 2 - off
    v = 2 * (d @ (n0 + n1)) / max(d @ d, 1e-12)
    nm = n0 + n1 - v * d
    nm = nm / np.linalg.norm(nm) if np.linalg.norm(nm) > 1e-9 else (n0 + n1) / np.linalg.norm(n0 + n1)
    return mid, nm


def level(parts, region):
    """One 1-to-4 pass over the region faces of every part. Returns the new region sets."""
    # joint smooth normal per position, from the stored normals of every copy
    acc = defaultdict(lambda: np.zeros(3))
    for pt in parts:
        for i, p in enumerate(pt.P):
            acc[key(p)] += pt.N[i]
    jn = {k: v / np.linalg.norm(v) for k, v in acc.items() if np.linalg.norm(v) > 1e-9}
    # edge -> (in-region count, total count) over both meshes, keyed by end positions
    tot, inr = defaultdict(int), defaultdict(int)
    for pi, pt in enumerate(parts):
        for fi, f in enumerate(pt.F):
            for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                e = frozenset((key(pt.P[a]), key(pt.P[b])))
                tot[e] += 1
                inr[e] += fi in region[pi]
    split = {e for e in tot if inr[e] == tot[e]}
    mids = {}                                    # edge key -> (pos, normal) shared by all copies
    new_region = []
    for pi, pt in enumerate(parts):
        vmid = {}                                # (a, b) sorted -> new vertex index in this part
        def mid(a, b):
            s = (min(a, b), max(a, b))
            if s in vmid:
                return vmid[s]
            ka, kb = key(pt.P[a]), key(pt.P[b])
            e = frozenset((ka, kb))
            if e not in mids:
                # ends ordered by key, so every copy of the edge computes the same point
                (k0, i0), (k1, i1) = sorted(((ka, a), (kb, b)))
                mids[e] = pn_mid(np.asarray(pt.P[i0]), np.asarray(pt.P[i1]), jn[k0], jn[k1])
            p, n = mids[e]
            w = {x: (pt.W[a].get(x, 0) + pt.W[b].get(x, 0)) / 2 for x in set(pt.W[a]) | set(pt.W[b])}
            t = pt.T[a] + pt.T[b]
            vc = (pt.VC[a] + pt.VC[b]) / 2 if pt.VC is not None else None
            vmid[s] = pt.add(p, n, t / max(np.linalg.norm(t), 1e-9), pt.TT[a], (pt.UV[a] + pt.UV[b]) / 2, vc, w)
            return vmid[s]
        F2, reg2 = [], set()
        for fi, f in enumerate(pt.F):
            if fi not in region[pi]:
                F2.append(f)
                continue
            v = list(f)
            sp = [frozenset((key(pt.P[v[k]]), key(pt.P[v[(k + 1) % 3]]))) in split for k in range(3)]
            m = [mid(v[k], v[(k + 1) % 3]) if sp[k] else None for k in range(3)]
            n = sum(sp)
            if n == 3:
                out = [[v[0], m[0], m[2]], [m[0], v[1], m[1]], [m[2], m[1], v[2]], [m[0], m[1], m[2]]]
            elif n == 0:
                out = [v]
            else:
                # rotate so edge 0 (v0-v1) is split
                r = sp.index(True) if n == 1 else [k for k in range(3) if sp[k] and sp[(k + 2) % 3]][0]
                v = v[r:] + v[:r]; m = m[r:] + m[:r]
                if n == 1:
                    out = [[v[0], m[0], v[2]], [m[0], v[1], v[2]]]
                else:                            # edges 0 and 2 split (v0-v1, v2-v0)
                    out = [[v[0], m[0], m[2]], [m[0], v[1], v[2]], [m[0], v[2], m[2]]]
            for g in out:
                reg2.add(len(F2)); F2.append(g)
        pt.F = F2
        new_region.append(reg2)
    return new_region


def renormal(parts, region, boundary_keys):
    """Area-weighted normals over both meshes' faces for region vertices not on its rim."""
    acc = defaultdict(lambda: np.zeros(3))
    for pi, pt in enumerate(parts):
        P = np.array(pt.P)
        sign = pt.sign
        for fi in region[pi]:
            a, b, c = pt.F[fi]
            fn = np.cross(P[b] - P[a], P[c] - P[a]) * sign
            for v in (a, b, c):
                acc[key(P[v])] += fn
    n = 0
    for pi, pt in enumerate(parts):
        for fi in region[pi]:
            for v in pt.F[fi]:
                k = key(pt.P[v])
                if k in boundary_keys or np.linalg.norm(acc[k]) < 1e-12:
                    continue
                nn = acc[k] / np.linalg.norm(acc[k])
                if pt.N[v] @ nn < 0.2:           # keep a hard edge the region doesn't own
                    continue
                pt.N[v] = nn
                t = pt.T[v] - (pt.T[v] @ nn) * nn
                pt.T[v] = t / max(np.linalg.norm(t), 1e-9)
                n += 1
    return n


def write(pt, dst):
    ch = pt.m.chunks[0]
    P = np.array(pt.P)
    coords = np.zeros((len(P), 16), np.uint8)
    coords[:pt.nv0] = ch["coords"]
    coords[:, :6] = pt.m.quantize(P).view(np.uint8).reshape(-1, 6)
    slot = {n: i for i, n in enumerate(pt.names)}
    for i in range(pt.nv0, len(P)):
        bn, bw = pack(pt.W[i])
        coords[i, 8:12] = [slot[x] if v else 0 for x, v in zip(bn, bw)]
        coords[i, 12:16] = bw
    ch["coords"] = coords
    ch["uv"] = enc_uv(np.array(pt.UV))
    ch["normals"] = enc_normals(np.array(pt.N), np.array(pt.NT), np.array(pt.T), np.array(pt.TT))
    if pt.VC is not None:
        ch["vc"] = np.clip(np.round(np.array(pt.VC)), 0, 255).astype(np.uint8)
    else:
        ch["vc"] = np.zeros((len(P), 8), np.uint8)
    ch["indices"] = np.array(pt.F, "<u2").ravel()
    pt.m.save(dst)


def main():
    tp, ti, lp, li, to, lo = sys.argv[1:7]
    R = float(sys.argv[7]) if len(sys.argv) > 7 else 0.07
    levels = int(sys.argv[8]) if len(sys.argv) > 8 else 2
    retail = Mesh.load(os.path.join(HERE, "..", "work", "scratch", "twa0", "twa0_01_wa__body.w2mesh"))
    torso = Part(tp, json.load(open(ti))["bones"] + eb.ALL, len(retail.positions(0)))
    legs = Part(lp, json.load(open(li))["bones"])
    parts = [torso, legs]
    E0 = np.array(eb.E0)
    region = []
    for pt in parts:
        P = np.array(pt.P)
        # winding vs stored normal (W3 is clockwise about it)
        f = pt.F[0]
        pt.sign = 1 if np.cross(P[f[1]] - P[f[0]], P[f[2]] - P[f[0]]) @ sum(pt.N[v] for v in f) > 0 else -1
        region.append({fi for fi, f in enumerate(pt.F)
                       if max(f) < pt.retail_n and np.linalg.norm(P[f].mean(0) - E0) < R})
    # rim: vertices also used by a face outside the region (in either mesh) keep their normal
    inside, outside = set(), set()
    for pi, pt in enumerate(parts):
        for fi, f in enumerate(pt.F):
            (inside if fi in region[pi] else outside).update(key(pt.P[v]) for v in f)
    rim = inside & outside
    print("region: torso %d tris, legs %d tris, rim %d positions" % (len(region[0]), len(region[1]), len(rim)))
    for _ in range(levels):
        region = level(parts, region)
    print("renormalled", renormal(parts, region, rim), "vertex copies")
    for pt, dst, name in ((torso, to, "torso"), (legs, lo, "legs")):
        print("%s LOD0: %d -> %d verts, %d tris" % (name, pt.nv0, len(pt.P), len(pt.F)))
        assert len(pt.P) < 65535
        write(pt, dst)
    print("->", to, lo)


if __name__ == "__main__":
    main()
