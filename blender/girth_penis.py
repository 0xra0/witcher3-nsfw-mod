"""Headless: shrink Geralt's shaft with scale keys on penis_01..03 (children inherit).

  blender -b in.blend --python girth_penis.py -- 0.85,0.85,0.92 out.blend

The l_01_mg__body shaft is ~5.4 cm across and her vulva ~2 cm, so a closed opening is cut
by the shaft (flat sliced labium) and an opened one shreds. The bones' long axis lies in
their local x-y plane, not on one axis, so only a uniform scale keeps the shape: each value
is that bone's local scale, and the product tapers from the base (which must still meet his
pubis) to the tip. Run after bend_penis.py: it aims by directions, so the aim is unchanged."""
import os, sys
import bpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nla_keys import _fcurves, track

S, OUT = sys.argv[sys.argv.index("--") + 1:]
G = bpy.data.objects["geralt:CMovingPhysicalAgentComponent25_ARM"]
# the import keys location and rotation only, so the scale channels are new, flat per strip
for k, s in enumerate(float(x) for x in S.split(",")):
    path = 'pose.bones["penis_%02d"].scale' % (k + 1)
    for strip in track(G).strips:
        fcs = _fcurves(strip.action)
        n_k = int(round(strip.frame_end)) - int(round(strip.frame_start)) + 1
        for fc in [fc for fc in fcs if fc.data_path == path]:
            fcs.remove(fc)
        for i in range(3):
            fc = fcs.new(path, index=i, group_name="penis_%02d" % (k + 1))
            fc.keyframe_points.add(n_k)
            fc.keyframe_points.foreach_set("co", [x for j in range(n_k) for x in (float(j), s)])
            fc.update()
bpy.ops.wm.save_as_mainfile(filepath=OUT)
