"""Headless: put the cooked game meshes into a scene blend, skinned to the cutscene armatures.

  blender -b scene.blend --python game_meshes.py -- meshes.json out.blend

meshes.json: {"meshes": [{"mesh": "...w2mesh",            # cooked, .1.buffer next to it
                          "bones": "...info.json",        # work/scratch/bones/meshinfo.py dump
                          "extra_bones": ["vag_0", ...],  # names of slots past the dump's list
                          "actor": "prostitute"}],        # or "geralt"
              "hide": ["twals_03_wa__body", ...]}         # scene meshes to hide (name parts)

The scene's own bodies are the retail meshes the witcher3_tools importer chose (twals_03 for
her, no penis groups on his), so they never show what the game draws. These are LOD0 of the
actual files we ship: positions, triangles, the stored normals (as custom normals, so seams
between body parts shade the way the game does) and the skin bytes as vertex groups, on the
actor's cutscene armature (which carries every deform bone, ring and penis bones included)."""
import json, os, sys
import bpy
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "tools"), os.path.join(HERE, "..", "work", "scratch", "bones")]
from mesh_geo import Mesh, dec_normals, dec_uv

CFG, OUT = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(CFG))
ARM = {"prostitute": "prostitute:CMovingPhysicalAgentComponent2_ARM",
       "geralt": "geralt:CMovingPhysicalAgentComponent25_ARM"}
sc = bpy.context.scene

for o in bpy.data.objects:
    if o.type == "MESH" and any(h in o.name for h in cfg.get("hide", [])):
        o.hide_render = o.hide_viewport = True

for spec in cfg["meshes"]:
    A = bpy.data.objects[ARM[spec["actor"]]]
    names = json.load(open(spec["bones"]))["bones"] + spec.get("extra_bones", [])
    m = Mesh.load(spec["mesh"])
    ch = m.chunks[0]
    P = m.positions(0)
    # W3 winds its triangles clockwise about the stored normals; Blender wants them CCW
    F = ch["indices"].reshape(-1, 3).astype(int)[:, ::-1]
    nrm = dec_normals(ch["normals"])[0]
    base = os.path.basename(spec["mesh"]).split(".")[0]
    me = bpy.data.meshes.new("game_" + base)
    me.from_pydata(P.tolist(), [], F.tolist())
    me.update()
    uv = dec_uv(ch["uv"])
    lay = me.uv_layers.new(name="UVMap")
    lv = np.array([l.vertex_index for l in me.loops])
    lay.data.foreach_set("uv", np.column_stack([uv[lv, 0], 1 - uv[lv, 1]]).ravel())   # W3 v runs down
    me.shade_smooth()
    me.normals_split_custom_set_from_vertices((nrm / np.linalg.norm(nrm, axis=1, keepdims=True)).tolist())
    ob = bpy.data.objects.new("game_" + base, me)
    sc.collection.objects.link(ob)
    ob.matrix_world = A.matrix_world
    groups, missing = {}, set()
    for i, row in enumerate(ch["coords"]):
        for b, w in zip(row[8:12], row[12:16]):
            if not w:
                continue
            n = names[b]
            if n not in A.data.bones:
                missing.add(n)
            g = groups.get(n) or groups.setdefault(n, ob.vertex_groups.new(name=n))
            g.add([i], w / 255.0, "ADD")
    mod = ob.modifiers.new("arm", "ARMATURE")
    mod.object = A
    mat = bpy.data.materials.new("skin_" + base)
    mat.diffuse_color = (0.85, 0.62, 0.52, 1) if spec["actor"] == "prostitute" else (0.75, 0.55, 0.45, 1)
    me.materials.append(mat)
    print("GAME %s: %d verts %d tris on %s, bones missing from the armature: %s"
          % (base, len(P), len(F), A.name, sorted(missing) or "none"))

bpy.ops.wm.save_as_mainfile(filepath=OUT)
