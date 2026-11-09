"""Undo wcc_lite's debug-mesh substitution in cooked entities.

  python3 tools/restore_imports.py <uncooked dir> <cooked dir>
When a mesh an entity references is not in the REDkit depot (Geralt's GeraltX body is
only in our bundle), wcc_lite cooks the handle as engine\\meshes\\editor\\debug.w2mesh.
For each cooked .w2ent with that import, the one CMesh path of the uncooked source that
the cooked file lacks is written back, in the template and in its flatCompiledData copy.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cr2wbuild import Cr2w
from ent_dangle import Chunk, split

DEBUG = "engine\\meshes\\editor\\debug.w2mesh"

def mesh_paths(f):
    return [p for p, cls, _ in f.imports if f.names[cls] == "CMesh"]

def fix(f, real):
    n = 0
    for imp in f.imports:
        if imp[0] == DEBUG:
            imp[0] = real; n += 1
    return n

def restore(src, dst):
    s = Cr2w(open(src, "rb").read()); c = Cr2w(open(dst, "rb").read())
    if DEBUG not in mesh_paths(c):
        return 0
    missing = [p for p in mesh_paths(s) if p not in mesh_paths(c)]
    assert len(missing) == 1, (dst, missing)
    n = fix(c, missing[0])
    T = [c.names[e[0]] for e in c.exports].index("CEntityTemplate")
    props, tail = split(c.c, c.exports[T][3]); new = Chunk(c)
    for name, typ, raw in props:
        if name == "flatCompiledData":
            inner = Cr2w(raw[12:]); n += fix(inner, missing[0]); ib = inner.bytes()
            new.prop(name, typ, struct.pack("<I", len(ib)) + ib); continue
        new.b += raw
    c.exports[T][3] = new.done(tail)
    open(dst, "wb").write(c.bytes())
    print("restored", missing[0], "x%d in" % n, dst)
    return n

if __name__ == "__main__":
    unc, ck = sys.argv[1], sys.argv[2]
    for root, _, files in os.walk(ck):
        for fn in files:
            if fn.endswith(".w2ent"):
                dst = os.path.join(root, fn)
                src = os.path.join(unc, os.path.relpath(dst, ck))
                if os.path.exists(src):
                    restore(src, dst)
