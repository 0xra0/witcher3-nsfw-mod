"""Headless: apply tools/crotch_weights.py to the prostitute body's vertex groups.

  blender -b in.blend --python reweight_her.py -- out.blend

Mirrors tools/reweight_crotch.py (which patches the cooked mesh the game uses) so the
tilt/shift/aim passes measure her crotch where the game will skin it."""
import os, sys
import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from crotch_weights import blend, crotch

OUT = sys.argv[sys.argv.index("--") + 1]
body = next(o for o in bpy.data.objects if o.type == "MESH" and "twals_03_wa__body" in o.name)
vg = body.vertex_groups
pel = vg["pelvis"].index
changed = 0
for v in body.data.vertices:
    c = crotch(v.co)
    if c < 1e-3:
        continue
    old = {g.group: g.weight for g in v.groups if g.weight > 0}
    tot = sum(old.values())
    if not tot or old.get(pel, 0) / tot >= 0.999:
        continue
    new = blend({b: w / tot for b, w in old.items()}, pel, c)
    for b, w in new.items():
        vg[b].add([v.index], w, "REPLACE")
    changed += 1
print("REWEIGHT", changed, "verts of", len(body.data.vertices))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
