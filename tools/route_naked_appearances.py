#!/usr/bin/env python3
"""Use each partner's existing naked appearance in every sex cutscene section.

This includes the opening sections and the censored fallback section so a
scene still selects the nude appearance if its flow takes an unexpected path.
Run --apply to patch workspace checkouts, or --verify to validate them.
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

from route_regular_scenes import PROJECT, SCENE_DIR, SCENES, parse, section_name, table, u16, u32


TARGET_SECTIONS = {*(f"sex_pre_0{i}" for i in (1, 2, 3, 4, 5)),
                   "sex_do_component", "sex_do_component_censored",
                   *(f"sex_after_0{i}" for i in (1, 2, 3, 4, 5))}


def appearance_offset(data: bytes, names: list[str], export: dict) -> int:
    prop_type, offset, size = export["props"]["actorOverrides"]
    if prop_type != "array:2,0,SCutsceneActorOverrideMapping" or u32(data, offset) != 1:
        raise ValueError("Unexpected actor override mapping")
    end = offset + size
    token = (struct.pack("<HHI", names.index("appearance"), names.index("CName"), 6))
    hits = [i + len(token) for i in range(offset + 4, end - len(token) - 1)
            if data[i:i + len(token)] == token]
    if len(hits) != 1:
        raise ValueError(f"Expected one appearance CName, found {len(hits)}")
    return hits[0]


def patch(data: bytes) -> tuple[bytes, list[str]]:
    names, exports = parse(data)
    modified = bytearray(data)
    changed = []
    seen = set()
    for export in exports:
        if export["class"] != "CStorySceneCutsceneSection":
            continue
        section = section_name(data, export)
        if section not in TARGET_SECTIONS:
            continue
        if section in seen:
            raise ValueError(f"Duplicate section {section}")
        seen.add(section)
        offset = appearance_offset(data, names, export)
        old_name = names[u16(data, offset)]
        if old_name.endswith("_panties"):
            new_name = old_name[:-8] + "_naked"
        elif old_name.endswith("_naked"):
            new_name = old_name
        else:
            new_name = old_name + "_naked"
        if new_name != old_name:
            if new_name not in names:
                raise ValueError(f"Missing appearance {new_name}")
            struct.pack_into("<H", modified, offset, names.index(new_name))
            changed.append(section)
        export_crc = zlib.crc32(modified[export["offset"]:export["offset"] + export["size"]])
        struct.pack_into("<I", modified, export["entry"] + 20, export_crc)
    if seen != TARGET_SECTIONS:
        raise ValueError(f"Missing sections: {TARGET_SECTIONS - seen}")
    exports_at, exports_count, _ = table(modified, 4)
    struct.pack_into("<I", modified, 40 + 4 * 12 + 8,
                     zlib.crc32(modified[exports_at:exports_at + exports_count * 24]))
    struct.pack_into("<I", modified, 32,
                     zlib.crc32(modified[:32] + b"\xef\xbe\xad\xde" + modified[36:160]))
    parse(modified)
    return bytes(modified), changed


def verify(data: bytes) -> None:
    names, exports = parse(data)
    seen = set()
    for export in exports:
        if export["class"] != "CStorySceneCutsceneSection":
            continue
        section = section_name(data, export)
        if section in TARGET_SECTIONS:
            seen.add(section)
            name = names[u16(data, appearance_offset(data, names, export))]
            if not name.endswith("_naked"):
                raise ValueError(f"{section} still uses {name}")
    if seen != TARGET_SECTIONS:
        raise ValueError(f"Missing sections: {TARGET_SECTIONS - seen}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    for name in SCENES:
        path = PROJECT / "depot" / SCENE_DIR / name
        data = path.read_bytes()
        if args.verify:
            verify(data)
            print(f"verified {name}")
        else:
            updated, changed = patch(data)
            if args.apply and changed:
                path.write_bytes(updated)
            print(f"{name}: {len(changed)} appearance overrides" + (" applied" if args.apply else " to change"))


if __name__ == "__main__":
    main()
