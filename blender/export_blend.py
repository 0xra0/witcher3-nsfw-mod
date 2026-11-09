"""Headless: export the cutscene in the opened .blend.
  blender -b scene.blend --python export_blend.py -- out.w2cutscene 'dlc\\...\\name.w2cutscene' [events_from.w2cutscene]

With events_from, the events and entToHideTags of that (vanilla) cutscene are written
into the export. The add-on's event writer only knows the generic fields (name, time,
animation, track, duration>0), so fade direction ("in") and item fields (category,
action, itemName_optional) would be lost; they are appended here from the source raw
fields. Root fades: only the first fade-out/fade-in pair and the final fade-out are
kept, because the mid-scene fades only existed to hide the vanilla camera cuts."""
import os, sys, bpy
from bl_ext.user_default.witcher3_tools.exporters import export_cutscene as ec
from bl_ext.user_default.witcher3_tools.exporters import export_anims as ea
from bl_ext.user_default.witcher3_tools.importers import import_cutscene as ic
from bl_ext.user_default.witcher3_tools.CR2W import anims_builder as ab
from bl_ext.user_default.witcher3_tools.CR2W.CR2W_types import PROPERTY

ARGS = sys.argv[sys.argv.index("--") + 1:]
OUT, REPO = ARGS[:2]
EVENTS_FROM = ARGS[2] if len(ARGS) > 2 else None
# W3_RIG_OVERRIDE="repo\\path.w2rig=/local/patched.w2rig": the exporter takes each actor's
# track list from the depot rig, so bones we added to the rig (penis chain) would be
# dropped; point it at the patched rig instead.
for spec in filter(None, os.environ.get("W3_RIG_OVERRIDE", "").split(";")):
    repo, local = spec.split("=", 1)
    _orig_rig_path = ea._resolve_cutscene_animation_rig_load_path
    def _rig_path(p, _repo=repo.lower().replace("/", "\\"), _local=local, _orig=_orig_rig_path):
        return _local if ea._normalize_repo_path(p).lower() == _repo else _orig(p)
    ea._resolve_cutscene_animation_rig_load_path = _rig_path
    print("RIG_OVERRIDE", repo, "->", local, len(ea._load_cutscene_rig_bone_names(local)), "bones")
GENERIC = {"eventName", "startTime", "animationName", "trackName"}
FIELD_TYPES = {"in": "Bool", "forceRelaxedState": "Bool", "duration": "Float",
               "category": "CName", "itemName_optional": "CName", "action": "EItemAction"}


def _payload(e, scope):
    rf = dict(e.raw_fields)
    return {"event_type": e.type_name, "event_name": rf.get("eventName", ""),
            "start_time": float(rf.get("startTime", 0.0) or 0.0),
            "duration": float(rf.get("duration", 0.0) or 0.0),
            "animation_name": rf.get("animationName", ""), "track_name": rf.get("trackName", ""),
            "event_scope": scope, "source_index": -1, "raw_fields": rf}


def _extra_prop(name, value):
    kind = FIELD_TYPES.get(name)
    if kind == "Bool":
        return PROPERTY(Value=bool(value), theName=name, theType="Bool")
    if kind == "Float":
        return PROPERTY(Value=float(value), theName=name, theType="Float")
    if kind == "CName":
        return ab._make_cname_prop(name, str(value))
    if kind:
        return ab._make_enum_prop(None, name, kind, str(value))
    raise ValueError("no type for event field %r" % name)


def install_event_hooks(source):
    tmpl = ic.loadCutsceneFile(source)
    fades = list(tmpl.animevents)
    root = fades[:2] + fades[-1:] if len(fades) > 3 else fades
    root_events = [_payload(e, "ROOT") for e in root]
    entry_events = [_payload(e, "ENTRY") for an in tmpl.animations for e in an.entries]
    hide_tags = list(tmpl.entToHideTags or [])

    ec._collect_scene_cutscene_events = lambda scene: (root_events, entry_events)

    make = ab._make_cutscene_event_prop

    def make_with_raw(event):
        prop = make(event)
        if prop is not None:
            have = {p.theName for p in prop.More}
            for name, value in (event.get("raw_fields") or {}).items():
                if name not in GENERIC and name not in have:
                    prop.More.append(_extra_prop(name, value))
        return prop
    ab._make_cutscene_event_prop = make_with_raw

    build = ab.build_w2cutscene

    def build_with_hide(*a, **kw):
        cr2w = build(*a, **kw)
        if hide_tags:
            root_chunk = next(c for c in cr2w.CHUNKS.CHUNKS if c.Type == "CCutsceneTemplate")
            root_chunk.PROPS.append(PROPERTY(
                theName="entToHideTags", theType="array:2,0,CName",
                elements=[ab._make_cname_prop("CName", t) for t in hide_tags]))
        return cr2w
    ab.build_w2cutscene = build_with_hide
    print("EVENTS root=%d entry=%d hide=%s" % (len(root_events), len(entry_events), hide_tags))


prefs = bpy.context.preferences.addons["bl_ext.user_default.witcher3_tools"].preferences
prefs.witcher_game_path = "/mnt/ssd/Games/The Witcher 3 Wild Hunt Remastered/game/game"
prefs.uncook_path = "/mnt/ssd/Witcher3Mod/witcher3-romance-mod/work/uncook"
bpy.context.scene.witcher_cutscene_export_repo_path = REPO
if EVENTS_FROM:
    install_event_hooks(EVENTS_FROM)
print("EXPORT", ec.export_w3_cutscene(bpy.context, OUT))
t = ic.loadCutsceneFile(OUT)
print("SHAPE actors=%d anims=%d" % (len(t.actorsDef or []), len(t.animations or [])))
for e in t.animevents:
    print("ROOTEV", e.type_name, e.raw_fields)
for an in t.animations:
    for e in an.entries:
        print("ENTRYEV", an.animation.name, e.type_name, e.raw_fields)
print("HIDE", t.entToHideTags)
