#!/usr/bin/env python3
"""Read Skyrim animations stored as Havok *tagfile* XML (<hktagfile>).

SLAL packs such as Billyy's LE ship every .hkx this way. PyNifly reads binary
packfiles and <hkpackfile> XML, but not tagfiles; this reads the tagfile fields
and reuses PyNifly's spline decompressor for the actual keyframes.

  hkx_tagfile.py <anim.hkx> [-o out.json]   dump bones + per-frame local TRS

Output JSON: {fps, num_frames, duration, bones:[name], annotations:[[t,text]],
             tracks:{bone:{t:[[x,y,z]..], r:[[x,y,z,w]..], s:[[x,y,z]..]}}}
Tracks are bone-local, Havok units (1 unit = 1 Skyrim unit ~ 1.428 cm).
"""
import json
import os
import struct
import sys
import xml.etree.ElementTree as ET

_NIFLY_HKX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          '..', 'vendor', 'io_scene_nifly', 'hkx')
sys.path.insert(0, os.environ.get('NIFLY_HKX', _NIFLY_HKX))
from anim_fo4 import _decompress_spline  # noqa: E402


def _real(text):
    """Tagfile reals are 'x41000000 <!-- 8.0 -->'; ElementTree drops the comment."""
    text = text.strip()
    if text.startswith('x'):
        return struct.unpack('<f', struct.pack('<I', int(text[1:9], 16)))[0]
    return float(text)


def _ints(elem):
    return [int(x) for x in (elem.text or '').split()]


def load_tagfile_animation(path):
    root = ET.parse(path).getroot()
    if root.tag != 'hktagfile':
        raise ValueError(f'{path}: not a tagfile (<{root.tag}>)')
    objects = {o.attrib['id']: o for o in root.iter('object')}
    anim = next((o for o in objects.values()
                 if o.attrib.get('type') == 'hkaSplineCompressedAnimation'), None)
    if anim is None:
        raise ValueError(f'{path}: no hkaSplineCompressedAnimation')

    f = {e.attrib.get('name'): e for e in anim}
    num_tracks = int(f['numberOfTransformTracks'].text)
    num_frames = int(f['numFrames'].text)
    tracks = _decompress_spline(
        bytes(_ints(f['data'])), num_tracks, num_frames,
        int(f['numBlocks'].text), int(f['maxFramesPerBlock'].text),
        _ints(f['blockOffsets']),
        int(f['maskAndQuantizationSize'].text) if 'maskAndQuantizationSize' in f else 0)

    # Track i animates the bone named by annotation track i (no explicit
    # transformTrackToBoneIndices in these files means identity mapping).
    bones, annotations = [], []
    for ref in f['annotationTracks'].findall('ref'):
        track = objects[ref.text.strip()]
        tf = {e.attrib.get('name'): e for e in track}
        bones.append(tf['trackName'].text if 'trackName' in tf else '')
        for s in (tf['annotations'].findall('struct') if 'annotations' in tf else []):
            sf = {e.attrib.get('name'): e for e in s}
            annotations.append([_real(sf['time'].text) if 'time' in sf else 0.0,
                                sf['text'].text if 'text' in sf else ''])

    frame_dur = _real(f['frameDuration'].text)
    return {
        'fps': round(1.0 / frame_dur, 3),
        'num_frames': num_frames,
        'duration': _real(f['duration'].text),
        'bones': bones,
        'annotations': sorted(annotations),
        'tracks': {b: {'t': t.translations, 'r': t.rotations, 's': t.scales}
                   for b, t in zip(bones, tracks)},
    }


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    a = load_tagfile_animation(sys.argv[1])
    if '-o' in sys.argv:
        with open(sys.argv[sys.argv.index('-o') + 1], 'w') as fh:
            json.dump(a, fh)
    print(f"{os.path.basename(sys.argv[1])}: {len(a['bones'])} bones, "
          f"{a['num_frames']} frames @ {a['fps']} fps, {a['duration']:.2f} s")


if __name__ == '__main__':
    main()
