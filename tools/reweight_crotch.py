"""Re-skin the prostitute body's crotch onto her pelvis in a cooked .w2mesh.1.buffer.

  python3 tools/reweight_crotch.py in.w2mesh.1.buffer out.w2mesh.1.buffer info.json
info.json: work/scratch/bones/meshinfo.py dump of the mesh (quantization, vertex blocks,
bone names). Only the skin bytes (u8 index x4 at vertex+8, u8 weight x4 at vertex+12) of
every LOD change; the .w2mesh itself is untouched. The falloff lives in crotch_weights.py.
"""
import json, struct, sys
from crotch_weights import blend, crotch


def main():
    src, dst, info = sys.argv[1:4]
    info = json.load(open(info))
    pel = info["bones"].index("pelvis")
    qs, qo = info["qs"], info["qo"]
    buf = bytearray(open(src, "rb").read())
    changed = 0
    for blk in info["infos"]:
        assert blk["nbpv"] == 4 and blk["vs"] == 16
        for i in range(blk["nv"]):
            o = blk["off"] + 16 * i
            q = [c / 65535 * s + f for c, s, f in zip(struct.unpack_from("<3H", buf, o), qs, qo)]
            c = crotch(q)
            if c < 1e-3:
                continue
            old = {}
            for b, w in zip(buf[o + 8:o + 12], buf[o + 12:o + 16]):
                if w:
                    old[b] = old.get(b, 0) + w / 255
            if old.get(pel, 0) >= 0.999:
                continue
            tot = sum(old.values())
            new = blend({b: w / tot for b, w in old.items()}, pel, c)
            slots = sorted(((b, w) for b, w in new.items() if w > 1e-3), key=lambda s: -s[1])[:4]
            t = sum(w for _, w in slots)
            qb = [int(round(255 * w / t)) for _, w in slots]
            qb[0] += 255 - sum(qb)
            buf[o + 8:o + 12] = bytes([b for b, _ in slots] + [0] * (4 - len(slots)))
            buf[o + 12:o + 16] = bytes(qb + [0] * (4 - len(slots)))
            changed += 1
    open(dst, "wb").write(buf)
    print("wrote", dst, len(buf), "reweighted verts", changed)


if __name__ == "__main__":
    main()
