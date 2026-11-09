"""Headless: import a retail cutscene, export it unchanged, report both files' shape."""
import sys, struct, time, bpy
GAME = "/mnt/ssd/Games/The Witcher 3 Wild Hunt Remastered/game/game"
UNCOOK = "/mnt/ssd/Witcher3Mod/witcher3-romance-mod/work/uncook"
CS, OUT, REPO = sys.argv[sys.argv.index("--") + 1:][:3]
prefs = bpy.context.preferences.addons["bl_ext.user_default.witcher3_tools"].preferences
prefs.witcher_game_path, prefs.uncook_path = GAME, UNCOOK
from bl_ext.user_default.witcher3_tools.importers import import_cutscene as ic
from bl_ext.user_default.witcher3_tools.exporters import export_cutscene as ec

def shape(path):
    data = open(path, "rb").read()
    t = ic.loadCutsceneFile(path)
    anims = getattr(t, "animations", None) or []
    return dict(version=struct.unpack_from("<I", data, 4)[0], size=len(data),
                actors=len(getattr(t, "actorsDef", None) or []), anims=len(anims),
                events=len(getattr(t, "animevents", None) or []))

ic.import_w3_cutscene(CS, auto_apply_selected_animations=True, import_burned_audio=False)
bpy.context.scene.witcher_cutscene_export_repo_path = REPO
t = time.time()
r = ec.export_w3_cutscene(bpy.context, OUT)
print("EXPORT", r, "%.1fs" % (time.time() - t))
print("ORIG", shape(CS))
print("NEW ", shape(OUT))
