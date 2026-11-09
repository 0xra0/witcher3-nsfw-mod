"""List or extract a W3 .bundle (POTATO70). Handles both TOC entry layouts:
0x140 (offset at +0x11c, comp at +0x13c) and 0x130 (offset at +0x110, comp at +0x124).
  python3 tools/unbundle.py file.bundle [outdir] [substring]"""
import os, struct, sys, zlib
try:
    import lz4.block as lz4b
except ImportError:
    lz4b = None

def entries(data):
    toc = struct.unpack_from("<I", data, 16)[0]
    for stride in (0x130, 0x140):
        if toc % stride == 0:
            break
    for i in range(toc // stride):
        o = 0x20 + i * stride
        name = data[o:o + 0x100].split(b"\0")[0].decode(errors="replace")
        if stride == 0x130:
            off, = struct.unpack_from("<I", data, o + 0x110)
            size, zsize = struct.unpack_from("<II", data, o + 0x118)
            comp, = struct.unpack_from("<I", data, o + 0x124)
        else:
            size, zsize, off = struct.unpack_from("<III", data, o + 0x114)
            comp, = struct.unpack_from("<I", data, o + 0x13c)
        yield name, off, size, zsize, comp

def unpack(raw, size, comp):
    if comp == 0:
        return raw
    if comp == 1:
        return zlib.decompress(raw)
    if comp in (4, 5) and lz4b:
        return lz4b.decompress(raw, uncompressed_size=size)
    raise ValueError("compression %d" % comp)

if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    assert data[:8] == b"POTATO70"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    sub = sys.argv[3] if len(sys.argv) > 3 else ""
    for name, off, size, zsize, comp in entries(data):
        if sub not in name:
            continue
        print(comp, size, name)
        if out:
            p = os.path.join(out, name.replace("\\", "/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(unpack(data[off:off + zsize], size, comp))
