"""Read and rewrite the geometry of a cooked W3 (next-gen) .w2mesh + .1.buffer.

Unlike meshbones.py / skin_entrance.py (same-size byte patches), this can change vertex and
index counts. Buffer layout per render chunk (renderChunks in cookedData): four streams,
each 16-byte aligned, then one index buffer at a 4096-aligned offset:
  coords 16 B (3 x u16 quantized pos, pad u16, 4 bone bytes, 4 weight bytes)
  uv      4 B (2 x half)
  normals 8 B (packed 10-bit normal + tangent)
  vc      8 B (colour + uv2)
Indices are u16, relative to the chunk's first vertex.

  m = Mesh.load(path)            # path.1.buffer is read next to it
  m.chunks[0]["coords"] ...      # numpy uint8 arrays [nv, stride]
  m.save(out_path)               # writes out_path and out_path.1.buffer
"""
import struct, zlib
import numpy as np
from cr2w import CR2W

STREAMS = (("coords", 16), ("uv", 4), ("normals", 8), ("vc", 8))
RC_FMT = "<B5IBIBHI4B"                      # one renderChunks record, 37 bytes


def _align(x, a):
    return (x + a - 1) // a * a


class Mesh:
    @classmethod
    def load(cls, path):
        m = cls()
        m.c = c = CR2W(open(path, "rb").read())
        m.buf = open(path + ".1.buffer", "rb").read()
        e = next(e for e in c.exports if c.names[e[0]] == "CMesh")
        pr, _ = c.props(e[4] + 1, e[4] + e[3])
        P = {q[0]: q for q in pr}
        # chunks: SMeshChunkPacked props we may rewrite (absent ones default to 0)
        m.chunk_fields = []
        n, = struct.unpack_from("<I", c.d, P["chunks"][2])
        p = P["chunks"][2] + 4
        for _ in range(n):
            sub, p = c.props(p + 1, P["chunks"][2] + P["chunks"][3])
            m.chunk_fields.append({s[0]: s[2] for s in sub})
        cd = P["cookedData"]
        sub, _ = c.props(cd[2] + 1, cd[2] + cd[3])
        m.cooked = {s[0]: s for s in sub}
        rc = m.cooked["renderChunks"][2] + 4
        nrc = c.d[rc]
        m.rc_off = rc + 1
        m.rc = [list(struct.unpack_from(RC_FMT, c.d, rc + 1 + 37 * i)) for i in range(nrc)]
        g = lambda k: struct.unpack_from("<I", c.d, m.cooked[k][2])[0]
        ib = g("indexBufferOffset")
        assert len(m.buf) == ib + g("indexBufferSize"), "buffer size mismatch"
        qs = [struct.unpack_from("<f", c.d, m.cooked["quantizationScale"][2] + 9 + 12 * i)[0] for i in range(3)]
        qo = [struct.unpack_from("<f", c.d, m.cooked["quantizationOffset"][2] + 9 + 12 * i)[0] for i in range(3)]
        m.qs, m.qo = np.array(qs), np.array(qo)
        m.chunks = []
        for r in m.rc:
            nv, ni = r[9], r[10]
            ch = {}
            for (name, sz), off in zip(STREAMS, r[1:5]):
                ch[name] = np.frombuffer(m.buf, np.uint8, nv * sz, off).reshape(nv, sz).copy()
            ch["indices"] = np.frombuffer(m.buf, "<u2", ni, ib + r[7]).copy()
            m.chunks.append(ch)
        # a stream at offset 0 past the first is absent (ls_02 legs have no vertex colours)
        m.absent = {n for k, (n, _) in enumerate(STREAMS) if k and all(r[1 + k] == 0 for r in m.rc)}
        k, (_, sz) = max((k, s) for k, s in enumerate(STREAMS) if s[0] not in m.absent)
        m.tail_pad = g("vertexBufferSize") - (m.rc[-1][1 + k] + sz * m.rc[-1][9])
        return m

    # positions -----------------------------------------------------------
    def positions(self, k):
        q = self.chunks[k]["coords"][:, :6].copy().view("<u2").astype(np.float64)
        return q / 65535 * self.qs + self.qo

    def quantize(self, p):
        q = np.round((np.asarray(p) - self.qo) / self.qs * 65535)
        assert q.min() >= 0 and q.max() <= 65535, "position outside the quantization box"
        return q.astype("<u2")

    # writing ---------------------------------------------------------------
    def save(self, path):
        buf, offs = bytearray(), []
        for ch in self.chunks:
            nv = len(ch["coords"])
            o = []
            for name, sz in STREAMS:
                if name in self.absent:
                    o.append(0)
                    continue
                assert ch[name].shape == (nv, sz), (name, ch[name].shape)
                buf += bytes(_align(len(buf), 16) - len(buf))
                o.append(len(buf)); buf += ch[name].tobytes()
            offs.append(o)
        vbs = len(buf) + self.tail_pad
        buf += bytes(vbs - len(buf))
        ibo = _align(vbs, 4096)
        buf += bytes(ibo - len(buf))
        iofs = []
        for ch in self.chunks:
            assert ch["indices"].max() < len(ch["coords"]) <= 65535
            iofs.append(len(buf) - ibo); buf += ch["indices"].astype("<u2").tobytes()
        ibs = len(buf) - ibo
        d = self.c.d
        fv = fi = 0
        for i, (ch, r, o, io) in enumerate(zip(self.chunks, self.rc, offs, iofs)):
            nv, ni = len(ch["coords"]), len(ch["indices"])
            r[1:5] = o; r[7] = io; r[9] = nv; r[10] = ni
            struct.pack_into(RC_FMT, d, self.rc_off + 37 * i, *r)
            f = self.chunk_fields[i]
            for k, v in (("numVertices", nv), ("numIndices", ni), ("firstVertex", fv), ("firstIndex", fi)):
                if k in f:
                    struct.pack_into("<I", d, f[k], v)
                else:
                    assert v == 0, ("chunk %d has no %s field to hold %d" % (i, k, v))
            fv += nv; fi += ni
        for k, v in (("vertexBufferSize", vbs), ("indexBufferSize", ibs), ("indexBufferOffset", ibo)):
            struct.pack_into("<I", d, self.cooked[k][2], v)
        # buffer table entry: flags, index, offset, diskSize, memSize, crc. The stored crc
        # is already stale in every mesh we shipped (meshbones/skin_entrance keep it) and
        # the game loads those, so it is left as is; only the sizes change.
        bo = self.c.tables[5][0]
        fl, ix, of, _, _, oc = struct.unpack_from("<6I", d, bo)
        struct.pack_into("<6I", d, bo, fl, ix, of, len(buf), len(buf), oc)
        # export crc (chunk data) and table crcs
        _fix_crcs(self.c)
        open(path, "wb").write(bytes(d))
        open(path + ".1.buffer", "wb").write(bytes(buf))


def _fix_crcs(c):
    d = c.d
    eo, ne, _ = c.tables[4]
    for i in range(ne):
        cls, fl, par, sz, off, tmpl, _ = struct.unpack_from("<HHIIIII", d, eo + 24 * i)
        struct.pack_into("<I", d, eo + 24 * i + 20, zlib.crc32(bytes(d[off:off + sz])) & 0xFFFFFFFF)
    for t in (4, 5):
        o, n, _ = c.tables[t]
        struct.pack_into("<I", d, 40 + 12 * t + 8, zlib.crc32(bytes(d[o:o + (24 * n)])) & 0xFFFFFFFF)


# stream codecs ----------------------------------------------------------------
def dec_uv(a):
    """uv stream -> [n,2] float (raw, v not flipped)."""
    return a.copy().view("<f2").reshape(-1, 2).astype(np.float64)


def enc_uv(uv):
    return np.asarray(uv, "<f2").reshape(-1, 2).view(np.uint8).reshape(-1, 4)


def _unpack10(w):
    w = w.astype(np.int64)
    xyz = np.stack([(w >> s) & 1023 for s in (0, 10, 20)], 1)
    return 2.0 * xyz / 1023.0 - 1.0, (w >> 30) & 3


def _pack10(v, top):
    q = np.clip(np.round((np.asarray(v) + 1.0) * 1023.0 / 2.0), 0, 1023).astype(np.int64)
    return (q[:, 0] | (q[:, 1] << 10) | (q[:, 2] << 20) | (np.asarray(top, np.int64) << 30)).astype("<u4")


def dec_normals(a):
    """normals stream -> (normal [n,3], normal top bits, tangent [n,3], tangent top bits)."""
    w = a.copy().view("<u4").reshape(-1, 2)
    n, nt = _unpack10(w[:, 0]); t, tt = _unpack10(w[:, 1])
    return n, nt, t, tt


def enc_normals(n, nt, t, tt):
    w = np.stack([_pack10(n, nt), _pack10(t, tt)], 1).astype("<u4")
    return w.view(np.uint8).reshape(-1, 8)
