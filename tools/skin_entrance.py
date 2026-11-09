"""Add the entrance ring (tools/entrance_bones.py) to the cooked woman rig and her body mesh.

  python3 tools/skin_entrance.py woman_base.w2rig twals_03_wa__body.w2mesh info.json outdir
info.json: work/scratch/bones/meshinfo.py dump of the mesh. The mesh's .1.buffer is read
next to it (pass the crotch-reweighted one). Writes outdir/woman_base.w2rig,
outdir/twals_03_wa__body.w2mesh and its .1.buffer. The ring bones get pelvis's
orientation, so each bind matrix is pelvis's with only the translation moved, and with
the ring at rest every vertex deforms exactly as before.
"""
import json, os, struct, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "work", "scratch", "bones"))
from cr2w import CR2W
from rigbones import add_bones, rebuild
from meshbones import enc_tail, parse_tail
import entrance_bones as eb


def quat_rot(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rig(src, dst):
    c = CR2W(open(src, "rb").read())
    chunks = [bytes(c.d[e[4]:e[4] + e[3]]) for e in c.exports]
    # pelvis rest from the rig's own data (dump.py layout): local = R^T (model - P)
    e = c.exports[0]
    pr, endp = c.props(e[4] + 1, e[4] + e[3])
    P = {q[0]: q for q in pr}
    nb, = struct.unpack_from("<I", c.d, P["bones"][2])
    p, names = P["bones"][2] + 4, []
    for _ in range(nb):
        sub, p2 = c.props(p + 1, 10 ** 9)
        names += [c.d[s[2] + 1:s[2] + s[3] - (0 if c.d[s[2]] & 0x80 else 1)].decode() for s in sub if s[0] == "name"]
        p = p2
    tf = struct.unpack_from("<12f", c.d, endp + 48 * names.index("pelvis"))
    R, P0 = quat_rot(tf[4:8]), np.array(tf[:3])
    new = [{"name": n, "parent": "pelvis", "pos": [float(v) for v in R.T @ (np.array(eb.bone_position(n)) - P0)],
            "rot": [0, 0, 0, 1]} for n in eb.ALL]
    extra = [b["name"] for b in new if b["name"] not in c.names]
    chunks[0] = add_bones(c, chunks[0], new, extra)
    out = rebuild(c, chunks, extra)
    open(dst, "wb").write(out)
    print("RIG", dst, len(out), "bones", nb, "->", nb + len(new), "pelvis", [round(v, 4) for v in P0])
    return P0


def mesh(src, dst, info, pelvis_rest):
    c = CR2W(open(src, "rb").read())
    d = c.d
    ei = next(i for i, e in enumerate(c.exports) if c.names[e[0]] == "CMesh")
    e = c.exports[ei]
    pr, endp = c.props(e[4] + 1, e[4] + e[3])
    t = parse_tail(d, endp)
    assert t["end"] == e[4] + e[3] and enc_tail(d, t) == bytes(d[endp:t["end"]]), "tail re-encode mismatch"
    bnames = [c.names[i] for i in t["names"]]
    assert bnames == info["bones"], "bone list differs from meshinfo dump"
    assert not set(eb.ALL) & set(bnames), "ring bones already in the mesh"
    pel = bnames.index("pelvis")
    M = np.array(t["mats"][pel]).reshape(4, 4)
    # Row-vector convention: local = p @ M; pelvis's bind must send its rest head to 0.
    assert np.abs(np.append(pelvis_rest, 1) @ M)[:3].max() < 2e-3, np.append(pelvis_rest, 1) @ M
    extra = [n for n in eb.ALL if n not in c.names]
    names = c.names + extra
    first = len(bnames)
    for k, n in enumerate(eb.ALL):
        Bk = np.array(eb.bone_position(n))
        Mk = M.copy(); Mk[3, :3] = -(Bk @ M[:3, :3])
        t["names"].append(names.index(n)); t["mats"].append(tuple(Mk.ravel()))
        t["eps"].append(t["eps"][pel]); t["map"].append(first + k)
    chunks = [bytes(d[x[4]:x[4] + x[3]]) for x in c.exports]
    chunks[ei] = bytes(d[e[4]:endp]) + enc_tail(d, t)
    out = rebuild(c, chunks, extra)
    buf = bytearray(open(src + ".1.buffer", "rb").read())
    qs, qo = np.array(info["qs"]), np.array(info["qo"])
    slot = {n: first + k for k, n in enumerate(eb.ALL)}
    changed, dropped = [0] * len(info["infos"]), 0.0
    for li, blk in enumerate(info["infos"]):
        assert blk["nbpv"] == 4 and blk["vs"] == 16
        for i in range(blk["nv"]):
            o = blk["off"] + 16 * i
            q = np.array(struct.unpack_from("<3H", buf, o)) / 65535 * qs + qo
            old = {}
            for b, w in zip(buf[o + 8:o + 12], buf[o + 12:o + 16]):
                if w:
                    old[b] = old.get(b, 0) + w / 255
            tot = sum(old.values())
            norm = {b: w / tot for b, w in old.items()}
            new = eb.take(norm, pel, tuple(q))
            if new == norm:
                continue
            new = {slot.get(b, b): w for b, w in new.items()}
            slots = sorted(((b, w) for b, w in new.items() if w > 1e-3), key=lambda s: -s[1])
            dropped = max(dropped, sum(w for _, w in slots[4:]))
            slots = slots[:4]
            s = sum(w for _, w in slots)
            qb = [int(round(255 * w / s)) for _, w in slots]
            qb[0] += 255 - sum(qb)
            buf[o + 8:o + 12] = bytes([b for b, _ in slots] + [0] * (4 - len(slots)))
            buf[o + 12:o + 16] = bytes(qb + [0] * (4 - len(slots)))
            changed[li] += 1
    open(dst, "wb").write(out)
    open(dst + ".1.buffer", "wb").write(buf)
    print("MESH", dst, len(out), "bones", len(t["names"]), "reskinned per LOD", changed,
          "largest weight dropped by the 4-bone limit %.3f" % dropped)


def main():
    rig_src, mesh_src, info, outdir = sys.argv[1:5]
    os.makedirs(outdir, exist_ok=True)
    P0 = rig(rig_src, os.path.join(outdir, "woman_base.w2rig"))
    mesh(mesh_src, os.path.join(outdir, os.path.basename(mesh_src)), json.load(open(info)), P0)


if __name__ == "__main__":
    main()
