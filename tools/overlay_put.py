"""Place uncooked sources into the REDkit overlay depot without writing through its symlinks.

  python3 tools/overlay_put.py <overlay r4data> <uncooked dir>
The overlay mirrors the REDkit depot with symlinks. For each file under <uncooked dir>,
every symlinked directory on its overlay path is replaced by a real directory of
symlinks to the same entries, and a symlinked target file is unlinked, before the copy.
So REDkit's own depot is never modified.
"""
import os, shutil, sys

def materialize(path):
    """Make `path` (a symlink to a directory) a real directory of per-entry symlinks."""
    target = os.path.realpath(path)
    os.unlink(path); os.mkdir(path)
    for e in os.listdir(target):
        os.symlink(os.path.join(target, e), os.path.join(path, e))

def put(ovl, rel, src):
    cur = ovl
    for part in rel.split(os.sep)[:-1]:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            materialize(cur)
        elif not os.path.exists(cur):
            os.mkdir(cur)
    dst = os.path.join(ovl, rel)
    if os.path.islink(dst):
        os.unlink(dst)
    assert os.path.realpath(dst).startswith(os.path.realpath(ovl)), dst
    shutil.copyfile(src, dst)
    return dst

if __name__ == "__main__":
    ovl, unc = sys.argv[1], sys.argv[2]
    for root, _, files in os.walk(unc):
        for f in files:
            src = os.path.join(root, f)
            print("overlay", put(ovl, os.path.relpath(src, unc), src))
