"""Re-tint one DXT1 texture from a W3 texture.cache into a new single-entry texture.cache.

  python3 -I tools/tint_texcache.py src.cache "depot\\path.xbm" r g b out.cache [mask.npy]

mask.npy (optional): float [0,1] array in texture space (row 0 = top, any size); each block gets
gain 1 + (gain - 1) * mask at its centre, so only the masked region is tinted, fading at the edge.

wcc_lite's texture importer needs a D3D12 device (none under headless wine), so instead of
re-importing, the existing DXT1 blocks are recoloured in place: every texel of a block is
an interpolation of its two RGB565 endpoints, so scaling the endpoints scales the whole
block the same way, with no re-compression loss. Endpoint order selects the block mode
(c0 > c1: 4 colours, else 3 colours + black), so blocks whose order flips are swapped and
their indices remapped. Layout follows the vanilla entry (chunks: zsize u32, size u32,
mip idx u8, zlib; mip table = u32 offsets from the entry start). Footer checksum = FNV-1a
64 over mip table + string table + entry table (matches wcc-built mod caches; WolvenKit-7
leaves the mip table out).
"""
import os, struct, sys, zlib
import numpy as np

M64 = (1 << 64) - 1


def checksum(b):
    h = 0xcbf29ce484222325
    for x in b:
        h ^= x
        h = ((h * 0x100000001b3) & M64) % M64
    return h


def read_entry(p, name):
    sz = os.path.getsize(p)
    f = open(p, 'rb')
    f.seek(sz - 32)
    foot = struct.unpack('<QIIII4sI', f.read(32))
    _, _, n, strsz, _, _, ver = foot
    f.seek(sz - 32 - n * 52)
    ents = f.read(n * 52)
    f.seek(sz - 32 - n * 52 - strsz)
    strs = f.read(strsz)
    for i in range(n):
        v = list(struct.unpack_from('<IiIIIIHHHHiiqBBBB', ents, 52 * i))
        if v[1] >= 0 and strs[v[1]:strs.index(b'\0', v[1])].decode() == name:
            f.seek(v[2] * 4096)
            return v, f.read(v[3]), ver
    raise SystemExit('not found: ' + name)


def block_gains(gain, mask, w, h):
    """Per-block (N, 3) gains for a w x h texel mip, or the plain gain without a mask."""
    if mask is None:
        return gain
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    ys = ((np.arange(bh) + 0.5) / bh * mask.shape[0]).astype(int)
    xs = ((np.arange(bw) + 0.5) / bw * mask.shape[1]).astype(int)
    m = mask[np.ix_(ys, xs)].reshape(-1, 1)
    return 1.0 + (np.asarray(gain)[None, :] - 1.0) * m


def tint_dxt1(raw, gain):
    b = np.frombuffer(raw, dtype='<u4').reshape(-1, 2).copy()
    c = b[:, 0]
    c0, c1, idx = (c & 0xffff).astype(np.int64), (c >> 16).astype(np.int64), b[:, 1].astype(np.int64)
    four = c0 > c1

    def scale(v):
        r, g, bl = (v >> 11) & 31, (v >> 5) & 63, v & 31
        gr, gg, gb = (gain[0], gain[1], gain[2]) if np.ndim(gain) == 1 else (gain[:, 0], gain[:, 1], gain[:, 2])
        r = np.clip(np.rint(r * gr), 0, 31).astype(np.int64)
        g = np.clip(np.rint(g * gg), 0, 63).astype(np.int64)
        bl = np.clip(np.rint(bl * gb), 0, 31).astype(np.int64)
        return (r << 11) | (g << 5) | bl
    n0, n1 = scale(c0), scale(c1)
    # Keep each block's mode: swap endpoints when the order flipped, remap the indices.
    flip4 = four & (n0 < n1)
    flip3 = ~four & (n0 > n1)
    swap = flip4 | flip3
    n0, n1 = np.where(swap, n1, n0), np.where(swap, n0, n1)
    hi = idx & 0xAAAAAAAA
    idx4 = idx ^ 0x55555555                              # 0<->1, 2<->3
    idx3 = idx ^ (~(hi >> 1) & 0x55555555)               # 0<->1 only (where bit 1 is clear)
    idx = np.where(flip4, idx4, np.where(flip3, idx3, idx))
    # 4-colour blocks whose endpoints collapsed would read as 3-colour + black: nudge apart.
    eq = four & (n0 == n1)
    up = eq & (n0 < 0xffff)
    n0 = np.where(up, n0 + 1, n0)
    n1 = np.where(eq & ~up, n1 - 1, n1)
    b[:, 0] = (n0 | (n1 << 16)).astype(np.uint32)
    b[:, 1] = idx.astype(np.uint32)
    return b.astype('<u4').tobytes(), int(swap.sum()), int(eq.sum())


def main():
    src, name, r, g, bl, out = sys.argv[1:7]
    gain = (float(r), float(g), float(bl))
    mask = np.load(sys.argv[7]).astype(float) if len(sys.argv) > 7 else None
    v, data, ver = read_entry(src, name)
    body, mips, pos = bytearray(), [], 0
    while pos < len(data) - 9:
        zs, us, mi = struct.unpack_from('<IIB', data, pos)
        if zs == 0:
            break
        raw = zlib.decompress(data[pos + 9:pos + 9 + zs])
        assert len(raw) == us and us % 8 == 0
        # The chunk's mip byte is not its level; find the level from the size. The last chunk
        # packs the small tail mips together: those get the mask's mean gain.
        lv = next((k for k in range(16) if us == max(1, ((v[6] >> k) + 3) // 4) * max(1, ((v[7] >> k) + 3) // 4) * 8), None)
        if lv is None:
            g = gain if mask is None else tuple(1.0 + (x - 1.0) * float(mask.mean()) for x in gain)
        else:
            g = block_gains(gain, mask, max(1, v[6] >> lv), max(1, v[7] >> lv))
        new, nswap, neq = tint_dxt1(raw, g)
        z = zlib.compress(new, 9)
        if body:
            mips.append(len(body))
        body += struct.pack('<IIB', len(z), len(new), mi) + z
        print('chunk mip %d size %d swapped %d nudged %d' % (mi, us, nswap, neq))
        pos += 9 + zs
    write_entry(out, name, v, ver, body, mips)


def write_entry(out, name, v, ver, body, mips):
    """Write a single-entry cache: body = the entry's chunks, mips = offsets of chunks 2..n."""
    v = list(v)
    nm = v[11] & 0xffff
    assert len(mips) == nm, (len(mips), nm)
    body = bytearray(body)
    csz = len(body)
    body += b'\0' * (-len(body) % 4096)
    strs = name.encode() + b'\0'
    v[1], v[2], v[3], v[10] = 0, 0, csz, 0
    ent = struct.pack('<IiIIIIHHHHiiqBBBB', *v)
    tables = struct.pack('<%dI' % len(mips), *mips) + strs + ent
    foot = struct.pack('<QIIII4sI', checksum(tables), len(body) // 4096, 1, len(strs), len(mips), b'HCXT', ver)
    open(out, 'wb').write(bytes(body) + tables + foot)
    print('wrote', out, os.path.getsize(out), 'entry', v)


if __name__ == '__main__':
    main()
