#!/bin/sh
# Cook + pack + metadatastore one override build dir with REDkit's wcc_lite under wine.
#   tools/cook_override.sh work/override_v2
# Expects <dir>/uncooked/animations/cutscenes/sex_scenes/sex_do_component.w2cutscene.
# wcc_lite only reads from <overlay>/r4data, so the uncooked file (and its _jp twin)
# are copied over the overlay's real files first. Produces <dir>/content/.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
W=$ROOT/work
B=$(cd "$1" && pwd)
SRC=$B/uncooked/animations/cutscenes/sex_scenes
OVL=$W/redkit_overlay/r4data/animations/cutscenes/sex_scenes

if pgrep -x witcher3.exe >/dev/null; then echo "witcher3.exe is running; not cooking" >&2; exit 1; fi

cp "$SRC/sex_do_component.w2cutscene" "$SRC/sex_do_component_jp.w2cutscene"
cp "$SRC/sex_do_component.w2cutscene" "$OVL/sex_do_component.w2cutscene"
cp "$SRC/sex_do_component.w2cutscene" "$OVL/sex_do_component_jp.w2cutscene"
# Other sources (entity/dyng) go into the overlay too, without writing through its symlinks.
python3 "$ROOT/tools/overlay_put.py" "$W/redkit_overlay/r4data" "$B/uncooked" | grep -v sex_scenes || true

win() { printf 'Z:%s\\' "$(printf %s "$1" | tr / '\\')"; }
rm -rf "$B/cooked" "$B/pack_in" "$B/content"
mkdir -p "$B/cooked" "$B/pack_in" "$B/content"

cd "$W/redkit_overlay/bin/x64_RedKit"
export WINEPREFIX=$W/wcc_prefix WINEDEBUG=-all
# No display: wcc_lite always hits a Halt assert (depotDirectory.cpp), and when it can
# open a window it shows an assert dialog nobody clicks, so the step "hangs" with an
# empty log. Headless, it logs the assert and carries on. Each step also gets a fresh
# wineserver and a timeout.
wcc() { env -u DISPLAY -u WAYLAND_DISPLAY timeout 300 nice wine wcc_lite.exe "$@"; rc=$?; wineserver -k || true; return $rc; }
wcc cook -platform=pc "-mod=$(win "$B/uncooked")" "-outdir=$(win "$B/cooked")" > "$B/cook.log" 2>&1 || true
python3 "$ROOT/tools/restore_imports.py" "$B/uncooked" "$B/cooked"
# everything wcc cooked (cutscene, plus any entity/dyng sources in uncooked/), minus its db
for d in "$B/cooked"/*/; do cp -r "$d" "$B/pack_in/"; done
# Already-cooked files (patched retail rig, re-skinned mesh + .buffer) go straight to pack.
if [ -d "$B/extra_cooked" ]; then cp -r "$B/extra_cooked/." "$B/pack_in/"; fi
wcc pack "-dir=$(win "$B/pack_in")" "-outdir=$(win "$B/content")" > "$B/pack.log" 2>&1 || true
wcc metadatastore "-path=$(win "$B/content")" > "$B/meta.log" 2>&1 || true

echo "cooked files: $(find "$B/cooked" -type f | wc -l)"
ls -la "$B/content"
strings "$B/content/blob0.bundle" | grep -o 'animations[^ ]*sex_do_component[a-z_]*\.w2cutscene' | sort -u
