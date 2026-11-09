#!/usr/bin/env python3
"""Patch extracted retail CR2W v164 scenes for a playable-format mod.

Input and output directories contain depot-relative paths. Use a fresh output
directory, then pack it with a Remastered-compatible bundle packer.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from route_naked_appearances import patch as patch_appearances, verify
from route_regular_scenes import SCENE_DIR, SCENES, patch_scene


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Root of extracted cooked retail files")
    parser.add_argument("output", type=Path, help="Fresh root for patched cooked files")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Output directory must be empty")
    for name in SCENES:
        relative = SCENE_DIR / name
        source = (args.input / relative).read_bytes()
        if struct.unpack_from("<I", source, 4)[0] != 164:
            raise ValueError(f"Expected retail CR2W v164: {relative}")
        routed, branches = patch_scene(source)
        patched, appearances = patch_appearances(routed)
        verify(patched)
        if len(branches) != 2 or len(appearances) != 11 or len(source) != len(patched):
            raise ValueError(f"Unexpected patch shape: {relative}")
        destination = args.output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(patched)
        print(f"{name}: 2 branch links, 11 appearance overrides, {len(patched)} bytes")


if __name__ == "__main__":
    main()
