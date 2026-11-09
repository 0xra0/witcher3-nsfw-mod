"""Headless: import the retail brothel sex cutscene into Blender and report what came in."""
import sys, time, bpy
from pathlib import Path

GAME = "/mnt/ssd/Games/The Witcher 3 Wild Hunt Remastered/game/game"
UNCOOK = "/mnt/ssd/Witcher3Mod/witcher3-romance-mod/work/uncook"
CS = sys.argv[sys.argv.index("--") + 1]
OUT = sys.argv[sys.argv.index("--") + 2]

prefs = bpy.context.preferences.addons["bl_ext.user_default.witcher3_tools"].preferences
prefs.witcher_game_path = GAME
prefs.uncook_path = UNCOOK
from bl_ext.user_default.witcher3_tools.importers import import_cutscene as ic

t = time.time()
tmpl = ic.loadCutsceneFile(CS)
print("ACTORS", [(a.name, a.template) for a in (getattr(tmpl, "actorsDef", None) or [])][:8])
ic.import_w3_cutscene(CS, auto_apply_selected_animations=True, import_burned_audio=False)
s = bpy.context.scene
print("TIME %.1fs frames %d-%d fps %s" % (time.time() - t, s.frame_start, s.frame_end, s.render.fps))
for o in bpy.data.objects:
    if o.type in {"ARMATURE", "CAMERA"}:
        ad = o.animation_data
        print("OBJ", o.type, o.name, "bones=%d" % len(o.data.bones) if o.type == "ARMATURE" else "",
              "nla=%d" % (len(ad.nla_tracks) if ad else 0))
print("MESHES", sum(o.type == "MESH" for o in bpy.data.objects), "ACTIONS", len(bpy.data.actions))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
