"""Merge W3 texture.cache files (e.g. tint_texcache.py outputs) into one.

  python3 -I tools/merge_texcache.py out.cache in1.cache in2.cache ...

Each input's data pages are appended in order; per entry, the string offset, start page and
mip-table start index (MipOffsetIndex) are shifted by what came before. Mip offsets are
relative to the entry's own start, so they are copied unchanged. Footer layout and checksum
as in tint_texcache.py. A name already taken by an earlier input is an error.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tint_texcache import checksum

EF = '<IiIIIIHHHHiiqBBBB'


def load(p):
    sz = os.path.getsize(p)
    f = open(p, 'rb')
    f.seek(sz - 32)
    _, pages, n, strsz, nmip, magic, ver = struct.unpack('<QIIII4sI', f.read(32))
    assert magic == b'HCXT', p
    f.seek(sz - 32 - n * 52 - strsz - nmip * 4)
    mips = list(struct.unpack('<%dI' % nmip, f.read(nmip * 4)))
    strs = f.read(strsz)
    ents = [list(struct.unpack_from(EF, f.read(52))) for _ in range(n)]
    f.seek(0)
    return f.read(pages * 4096), mips, strs, ents, ver


def main():
    out, ins = sys.argv[1], sys.argv[2:]
    body, mips, strs, ents, names, ver = b'', [], b'', [], set(), None
    for p in ins:
        b, m, s, e, v = load(p)
        assert ver in (None, v), (p, v, ver)
        ver = v
        for x in e:
            nm = s[x[1]:s.index(b'\0', x[1])]
            assert nm not in names, nm
            names.add(nm)
            x[1] += len(strs)
            x[2] += len(body) // 4096
            x[10] += len(mips)
            ents.append(x)
            print('%s: %s page %d' % (os.path.basename(p), nm.decode(), x[2]))
        body, mips, strs = body + b, mips + m, strs + s
    tables = struct.pack('<%dI' % len(mips), *mips) + strs + b''.join(struct.pack(EF, *x) for x in ents)
    foot = struct.pack('<QIIII4sI', checksum(tables), len(body) // 4096, len(ents), len(strs), len(mips), b'HCXT', ver)
    open(out, 'wb').write(body + tables + foot)
    print('wrote', out, os.path.getsize(out), len(ents), 'entries')


if __name__ == '__main__':
    main()
