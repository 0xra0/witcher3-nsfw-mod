"""Give Geralt's bare-legs item a dyng dangle that the body mesh is skinned to.

  python3 tools/ent_dangle.py legs.w2ent out.w2ent dyng_depot_path [gravity speed]
legs.w2ent: REDkit's uncooked items\\bodyparts\\geralt_items\\legs\\bare\\l_01_mg__body.w2ent.
Appends, in both the template and its flatCompiledData copy, the medallion item's pattern
(t_01_mg__body_medalion.w2ent): CAnimDangleComponent -> CAnimDangleConstraint_Dyng, plus a
CMeshSkinningAttachment from the dangle to the existing mesh component. Existing exports
keep their indices; only the mesh's parent-attachment list, its transformParent and the
entity's component list are edited.
"""
import os, struct, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cr2wbuild import Cr2w

IDENT = struct.pack("<16f", *[1.0 if r == k else 0.0 for r in range(4) for k in range(4)])

def ascii_str(s):
    b = s.encode("ascii"); assert len(b) < 64
    return bytes([0x80 | len(b)]) + b

class Chunk:
    def __init__(self, f):
        self.f = f; self.b = bytearray(b"\0")
    def prop(self, name, typ, value):
        self.b += struct.pack("<HHI", self.f.name(name), self.f.name(typ), len(value) + 4) + value
        return self
    def done(self, tail=b""):
        return bytes(self.b + b"\0\0" + tail)

def split(c, chunk):
    """chunk bytes -> (list of (name, type, raw prop bytes), tail)."""
    out = []; p = 1
    while True:
        ni, = struct.unpack_from("<H", chunk, p)
        if ni == 0:
            return out, chunk[p + 2:]
        ti, sz = struct.unpack_from("<HI", chunk, p + 2)
        out.append((c.names[ni], c.names[ti], chunk[p:p + 4 + sz])); p += 4 + sz

def patch(data, dyng_path, gravity, speed):
    f = Cr2w(data)
    cls = [f.names[e[0]] for e in f.exports]
    E = cls.index("CItemEntity") + 1
    M = cls.index("CMeshComponent") + 1
    dyng = f.imp(dyng_path, "CDyngResource")
    D, A, K = len(f.exports) + 1, len(f.exports) + 2, len(f.exports) + 3
    ptr = lambda i: struct.pack("<i", i)
    f.add_export("CAnimDangleComponent", E, Chunk(f)
        .prop("constraint", "ptr:IAnimDangleConstraint", ptr(K))
        .prop("name", "String", ascii_str("penis_dangle"))
        .prop("guid", "CGUID", uuid.uuid5(uuid.NAMESPACE_URL, "w3romance/penis_dangle").bytes)
        .done(struct.pack("<III", 0, 1, A) + IDENT))
    f.add_export("CMeshSkinningAttachment", D, Chunk(f)
        .prop("parent", "ptr:CNode", ptr(D)).prop("child", "ptr:CNode", ptr(M)).done())
    f.add_export("CAnimDangleConstraint_Dyng", D, Chunk(f)
        .prop("dyng", "handle:CDyngResource", ptr(dyng))
        .prop("gravity", "Float", struct.pack("<f", gravity))
        .prop("speed", "Float", struct.pack("<f", speed)).done())
    # mesh: transformParent -> attachment, and the attachment in its parent-attachment list
    props, tail = split(f.c, f.exports[M - 1][3])
    assert "transformParent" not in [n for n, _, _ in props]
    assert tail[:8] == b"\0" * 8, tail[:8].hex()
    new = Chunk(f)
    for n, t, raw in props:
        if n == "guid":
            new.prop("transformParent", "ptr:CHardAttachment", ptr(A))
        new.b += struct.pack("<HH", f.name(n), f.name(t)) + raw[4:]
    f.exports[M - 1][3] = new.done(struct.pack("<II", 1, A) + tail[4:])
    # entity: component list (count byte + u32 indices, near the end of its tail) gains D
    ch = f.exports[E - 1][3]
    pat = b"\x01" + struct.pack("<I", M)
    k = ch.rfind(pat); assert k > len(ch) - 16, "component list not found"
    f.exports[E - 1][3] = ch[:k] + b"\x02" + struct.pack("<II", M, D) + ch[k + len(pat):]
    return f

if __name__ == "__main__":
    src, dst, dyng_path = sys.argv[1:4]
    gravity, speed = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (1.0, 0.4)
    outer = patch(open(src, "rb").read(), dyng_path, gravity, speed)
    # template chunk: swap in the patched flatCompiledData copy
    T = [outer.names[e[0]] for e in outer.exports].index("CEntityTemplate")
    props, tail = split(outer.c, outer.exports[T][3])
    new = Chunk(outer)
    for n, t, raw in props:
        if n == "flatCompiledData":
            inner = patch(raw[12:], dyng_path, gravity, speed).bytes()
            new.prop(n, t, struct.pack("<I", len(inner)) + inner); continue
        new.b += struct.pack("<HH", outer.name(n), outer.name(t)) + raw[4:]
    outer.exports[T][3] = new.done(tail)
    open(dst, "wb").write(outer.bytes())
    print("wrote", dst)
