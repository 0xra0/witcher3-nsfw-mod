#!/usr/bin/env python3
"""Patch the three Belles of Beauclair cooked scenes for the romance playtest."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from route_regular_scenes import parse, prop_u32, section_name, table
from route_naked_appearances import patch as patch_appearances, verify as verify_appearances


ROOT = Path(__file__).resolve().parents[1]
RELATIVE = Path("dlc/bob/data/living_world/merchants")
SCENES = tuple(f"shop_47_sex_girl_{i}.w2scene" for i in (1, 2, 3))


def patch_routes(original: bytes) -> bytes:
    _, exports = parse(original)
    sections = {
        i + 1: section_name(original, export)
        for i, export in enumerate(exports)
        if export["class"] == "CStorySceneCutsceneSection"
    }
    conditions = [(i, export) for i, export in enumerate(exports)
                  if export["class"] == "CStorySceneFlowCondition"]
    if len(conditions) != 2:
        raise ValueError(f"Expected two flow conditions, found {len(conditions)}")
    censored_links = 0
    patched = bytearray(original)
    for i, export in conditions:
        if "comment" in export["props"]:
            kind, offset, size = export["props"]["comment"]
            if kind != "String" or original[offset + 1:offset + size] != b"release_jp >= 1":
                raise ValueError("Unexpected condition comment")
        true_link, true_offset = prop_u32(original, export, "trueLink")
        false_link, _ = prop_u32(original, export, "falseLink")
        if true_link == false_link:
            raise ValueError("Scene condition already merged")
        true_element = exports[true_link - 1]
        if true_element["class"] != "CStorySceneLinkElement":
            raise ValueError("Unexpected true-link class")
        next_id, _ = prop_u32(original, true_element, "nextLinkElement")
        censored_links += sections.get(next_id) == "sex_do_component_censored"
        struct.pack_into("<I", patched, true_offset, false_link)
        struct.pack_into("<I", patched, export["entry"] + 20,
                         zlib.crc32(patched[export["offset"]:export["offset"] + export["size"]]))
    if censored_links != 1:
        raise ValueError(f"Expected one direct censored branch, found {censored_links}")
    exports_at, exports_count, _ = table(patched, 4)
    struct.pack_into("<I", patched, 40 + 4 * 12 + 8,
                     zlib.crc32(patched[exports_at:exports_at + exports_count * 24]))
    struct.pack_into("<I", patched, 32,
                     zlib.crc32(patched[:32] + b"\xef\xbe\xad\xde" + patched[36:160]))
    parse(patched)
    return bytes(patched)


def main() -> None:
    source_root = Path("work/retail_bob_unpacked")
    output_root = Path("work/novigrad_beauclair_playtest_v05_cooked")
    for name in SCENES:
        source = source_root / RELATIVE / name
        output = output_root / RELATIVE / name
        original = source.read_bytes()
        routes = patch_routes(original)
        result, changed = patch_appearances(routes)
        verify_appearances(result)
        if len(result) != len(original) or len(changed) != 11:
            raise ValueError(f"Unexpected patch size/count for {name}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(result)
        print(f"{name}: two routes, {len(changed)} appearance overrides, {len(result)} bytes")


if __name__ == "__main__":
    main()
