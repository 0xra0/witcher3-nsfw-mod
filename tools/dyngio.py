"""Read/write the CDyngResource chunk of an uncooked .w3dyng, using an existing file as
the CR2W template (its name table already holds every property/type name needed).
  decode(path) -> (CR2W, [(prop, type, value)])     encode(c, props) -> file bytes
Values: arrays -> lists; Matrix -> 4x4 nested list rows X,Y,Z,W; String -> str."""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work", "scratch", "bones"))
from cr2w import CR2W
from rigbones import rebuild

AX = "XYZW"

def vlq(d, p):
    b = d[p]; neg = b & 0x80; more = b & 0x40; v = b & 0x3F; p += 1; sh = 6
    while more:
        b = d[p]; v |= (b & 0x7F) << sh; more = b & 0x80; p += 1; sh += 7
    return (-v if neg else v), p

def enc_vlq(v):
    neg = v < 0; v = abs(v)
    out = bytearray([(0x80 if neg else 0) | (v & 0x3F) | (0x40 if v > 0x3F else 0)]); v >>= 6
    while v:
        out.append((v & 0x7F) | (0x80 if v > 0x7F else 0)); v >>= 7
    return bytes(out)

class Codec:
    def __init__(self, c):
        self.c = c; self.ix = {n: i for i, n in enumerate(c.names)}
    # --- decode
    def struct(self, d, p):
        assert d[p] == 0; p += 1; out = []
        while True:
            ni, = struct.unpack_from("<H", d, p)
            if ni == 0: return out, p + 2
            ti, sz = struct.unpack_from("<HI", d, p + 2)
            n, t = self.c.names[ni], self.c.names[ti]
            v, q = self.value(t, d, p + 8)
            assert q == p + 4 + sz, (n, t, q, p + 4 + sz)
            out.append((n, t, v)); p = q
    def value(self, t, d, p):
        if t.startswith("array:"):
            el = t.split(",", 2)[2]; n, = struct.unpack_from("<I", d, p); p += 4; out = []
            for _ in range(n):
                v, p = self.value(el, d, p); out.append(v)
            return out, p
        if t == "Float": return struct.unpack_from("<f", d, p)[0], p + 4
        if t == "Int32": return struct.unpack_from("<i", d, p)[0], p + 4
        if t == "String":
            n, p = vlq(d, p)
            if n < 0: return d[p:p - n].decode("latin1"), p - n
            return d[p:p + 2 * n].decode("utf-16le"), p + 2 * n
        if t == "CDateTime": return bytes(d[p:p + 8]), p + 8
        if t in ("Matrix", "Vector"): return self.struct(d, p)
        raise ValueError(t)
    # --- encode
    def e_struct(self, props):
        b = bytearray(b"\0")
        for n, t, v in props:
            vb = self.e_value(t, v)
            b += struct.pack("<HHI", self.ix[n], self.ix[t], len(vb) + 4) + vb
        return bytes(b + b"\0\0")
    def e_value(self, t, v):
        if t.startswith("array:"):
            el = t.split(",", 2)[2]
            return struct.pack("<I", len(v)) + b"".join(self.e_value(el, x) for x in v)
        if t == "Float": return struct.pack("<f", v)
        if t == "Int32": return struct.pack("<i", v)
        if t == "String":
            if v == "" : return enc_vlq(0)
            try:
                raw = v.encode("ascii"); return enc_vlq(-len(raw)) + raw
            except UnicodeEncodeError:
                return enc_vlq(len(v)) + v.encode("utf-16le")
        if t == "CDateTime": return bytes(v)
        if t in ("Matrix", "Vector"): return self.e_struct(v)
        raise ValueError(t)

def mat(rows):
    """4x4 rows -> Matrix struct props."""
    return [(AX[r], "Vector", [(AX[k], "Float", float(rows[r][k])) for k in range(4)]) for r in range(4)]

def unmat(m):
    return [[dict((n, v) for n, _, v in vec)[a] for a in AX] for _, _, vec in m]

def decode(path):
    c = CR2W(open(path, "rb").read()); k = Codec(c)
    e = c.exports[0]; o, sz = e[4], e[3]
    props, end = k.struct(c.d, o)
    tail = bytes(c.d[end:o + sz])
    return c, props, tail

def encode(c, props, tail=b""):
    k = Codec(c)
    chunk = k.e_struct(props) + tail
    chunks = [chunk] + [bytes(c.d[e[4]:e[4] + e[3]]) for e in c.exports[1:]]
    return rebuild(c, chunks, [])

if __name__ == "__main__":
    c, props, tail = decode(sys.argv[1])
    out = encode(c, props, tail)
    orig = bytes(c.d)
    print("tail", tail.hex(), "roundtrip identical:", out == orig, len(out), len(orig))
    if out != orig:
        i = next(i for i in range(min(len(out), len(orig))) if out[i] != orig[i]); print("first diff", i)
