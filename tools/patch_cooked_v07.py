#!/usr/bin/env python3
"""Build the v0.7 cooked scene tree from extracted retail CR2W v164 scenes.

v0.7 = v0.6 (regular routing + `_naked` actorOverrides) + rewire_appearance_calls,
which moves the scene's AppearanceChange `_naked` call to the start and the
`_panties` call to the exit. Pack the output with `w3edit bundle pack`.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from patch_beauclair_scenes import RELATIVE as BOB_DIR, SCENES as BOB_SCENES, patch_routes
from rewire_appearance_calls import check_flow, rewire
from route_naked_appearances import patch as patch_overrides, verify as verify_overrides
from route_regular_scenes import SCENE_DIR, SCENES, patch_scene


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blob_root", type=Path, help="Retail files extracted from blob.bundle")
    parser.add_argument("bob_root", type=Path, help="Retail files extracted from bob.bundle")
    parser.add_argument("output", type=Path, help="Fresh root for patched cooked files")
    parser.add_argument("--only-main", action="store_true",
                        help="Test build: play only sex_do_component (no lead-in/after sections)")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Output directory must be empty")
    jobs = [(args.blob_root, SCENE_DIR / n, lambda d: patch_scene(d)[0]) for n in SCENES]
    jobs += [(args.bob_root, BOB_DIR / n, patch_routes) for n in BOB_SCENES]
    for root, relative, route in jobs:
        source = (root / relative).read_bytes()
        if struct.unpack_from("<I", source, 4)[0] != 164:
            raise ValueError(f"Expected retail CR2W v164: {relative}")
        patched, overrides = patch_overrides(route(source))
        verify_overrides(patched)
        patched, links = rewire(patched, args.only_main)
        if len(overrides) != 11 or len(patched) != len(source):
            raise ValueError(f"Unexpected patch shape: {relative}")
        sections = check_flow(patched)
        if args.only_main and sections != ["sex_do_component"]:
            raise ValueError(f"{relative.name}: other sections still reachable: {sections}")
        destination = args.output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(patched)
        print(f"{relative.name}: {len(links)} links rewired, {len(sections)} sections naked")


if __name__ == "__main__":
    main()
