"""Dump one DXT1 texture from a W3 texture.cache as a .dds (all mips the cache stores).

  python3 -I tools/texcache_dds.py src.cache "depot\\path.xbm" out.dds

Chunk layout and entry lookup as in tint_texcache.py. The last chunk packs the tail mips
together, so the DDS mip count is the number of whole-mip chunks plus that tail.
"""
import os, struct, sys, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tint_texcache import read_entry


def chunks(data):
    pos = 0
    while pos < len(data) - 9:
        zs, us, mi = struct.unpack_from('<IIB', data, pos)
        if zs == 0:
            break
        raw = zlib.decompress(data[pos + 9:pos + 9 + zs])
        assert len(raw) == us
        yield raw
        pos += 9 + zs


def dds_header(w, h, mips):
    hdr = struct.pack('<4sIIIIIII44x', b'DDS ', 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000,
                      h, w, max(1, (w + 3) // 4) * 8 * max(1, (h + 3) // 4), 0, mips)
    hdr += struct.pack('<II4s20x', 32, 0x4, b'DXT1')
    return hdr + struct.pack('<I16x', 0x1000 | 0x400000 | 0x8)


def main():
    src, name, out = sys.argv[1:4]
    v, data, _ = read_entry(src, name)
    w, h, nmips = v[6], v[7], v[8]
    body = b''.join(chunks(data))
    open(out, 'wb').write(dds_header(w, h, nmips) + body)
    print('%dx%d mips %d -> %s (%d bytes)' % (w, h, nmips, out, len(body)))


if __name__ == '__main__':
    main()
