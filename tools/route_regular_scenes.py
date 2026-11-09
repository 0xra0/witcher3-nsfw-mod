#!/usr/bin/env python3
"""Route the six Novigrad brothel scenes through their regular cutscenes.

This is a narrow CR2W patch: only the two release_jp condition true-link
references in each scene are changed. The regular false branch remains intact.
Run without flags to preview, --apply to write workspace checkouts, or --verify
to check that all six patched checkouts match the expected bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import zlib
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REDKIT_DEPOT = Path("/mnt/sata/Games/The Witcher 3 REDkit/r4data")
SCENE_DIR = Path("gameplay/community/dialogues/brothels")
SCENES = (
    "brothels_novigrad_brothel_district_peggleg_peggys_girl_01_sex.w2scene",
    "brothels_novigrad_brothel_district_peggleg_peggys_girl_02_sex.w2scene",
    "brothels_novigrad_brothel_district_peggleg_peggys_girl_03_sex.w2scene",
    "brothels_novigrad_rich_district_passiflora_girl_01_sex.w2scene",
    "brothels_novigrad_rich_district_passiflora_girl_02_sex.w2scene",
    "brothels_novigrad_rich_district_passiflora_girl_03_sex.w2scene",
)


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def table(data: bytes, index: int) -> tuple[int, int, int]:
    return struct.unpack_from("<III", data, 40 + index * 12)


def parse(data: bytes) -> tuple[list[str], list[dict]]:
    if data[:4] != b"CR2W" or u32(data, 4) not in (161, 164):
        raise ValueError("Unexpected CR2W magic or version")
    strings_at, strings_size, strings_crc = table(data, 0)
    strings = data[strings_at:strings_at + strings_size]
    if zlib.crc32(strings) != strings_crc:
        raise ValueError("String table CRC mismatch")
    names_at, names_count, names_crc = table(data, 1)
    if zlib.crc32(data[names_at:names_at + names_count * 8]) != names_crc:
        raise ValueError("Name table CRC mismatch")
    names = []
    for i in range(names_count):
        offset = u32(data, names_at + i * 8)
        end = strings.find(b"\0", offset)
        if end < 0:
            raise ValueError("Unterminated name")
        names.append(strings[offset:end].decode("utf-8"))
    exports_at, exports_count, exports_crc = table(data, 4)
    if zlib.crc32(data[exports_at:exports_at + exports_count * 24]) != exports_crc:
        raise ValueError("Export table CRC mismatch")
    exports = []
    for i in range(exports_count):
        klass, _, _, size, offset, _, crc = struct.unpack_from(
            "<HHIIIII", data, exports_at + i * 24
        )
        if offset + size > len(data) or zlib.crc32(data[offset:offset + size]) != crc:
            raise ValueError(f"Export {i + 1} has invalid bounds or CRC")
        props = {}
        pos = offset + 1  # CR2W export payload begins with a marker byte.
        while pos + 8 <= offset + size:
            prop_name = u16(data, pos)
            if prop_name == 0:
                break
            prop_type = u16(data, pos + 2)
            prop_size = u32(data, pos + 4)
            if (
                prop_name >= len(names) or prop_type >= len(names)
                or prop_size < 4 or pos + 4 + prop_size > offset + size
            ):
                raise ValueError(f"Invalid property in export {i + 1}")
            props[names[prop_name]] = (names[prop_type], pos + 8, prop_size - 4)
            pos += 4 + prop_size
        exports.append({"class": names[klass], "offset": offset, "size": size,
                        "entry": exports_at + i * 24, "props": props})
    if zlib.crc32(data[:32] + b"\xef\xbe\xad\xde" + data[36:160]) != u32(data, 32):
        raise ValueError("Header CRC mismatch")
    return names, exports


def prop_u32(data: bytes, export: dict, name: str) -> tuple[int, int]:
    prop_type, offset, size = export["props"][name]
    if size != 4 or not prop_type.startswith("ptr:"):
        raise ValueError(f"Unexpected {name} property format")
    return u32(data, offset), offset


def section_name(data: bytes, export: dict) -> str:
    prop_type, offset, size = export["props"]["sectionName"]
    if prop_type != "String" or size < 1:
        raise ValueError("Unexpected sectionName format")
    length = data[offset] & 0x7f
    if length != size - 1:
        raise ValueError("Unexpected sectionName length")
    return data[offset + 1:offset + size].decode("utf-8")


def patch_scene(original: bytes) -> tuple[bytes, list[tuple[int, int, int]]]:
    _, exports = parse(original)
    sections = {
        i + 1: section_name(original, export)
        for i, export in enumerate(exports)
        if export["class"] == "CStorySceneCutsceneSection"
    }
    if list(sections.values()).count("sex_do_component") != 1 or list(sections.values()).count("sex_do_component_censored") != 1:
        raise ValueError("Expected exactly one regular and one censored component")
    conditions = []
    for i, export in enumerate(exports):
        if export["class"] != "CStorySceneFlowCondition":
            continue
        prop_type, offset, size = export["props"]["comment"]
        if prop_type != "String" or original[offset + 1:offset + size] != b"release_jp >= 1":
            raise ValueError("Unexpected flow condition")
        true_link, true_offset = prop_u32(original, export, "trueLink")
        false_link, _ = prop_u32(original, export, "falseLink")
        if not (1 <= true_link <= len(exports) and 1 <= false_link <= len(exports)):
            raise ValueError("Invalid flow link")
        conditions.append((i, true_link, false_link, true_offset))
    if len(conditions) != 2:
        raise ValueError(f"Expected two release_jp conditions, found {len(conditions)}")
    last_true = exports[conditions[-1][1] - 1]
    next_id, _ = prop_u32(original, last_true, "nextLinkElement")
    if sections.get(next_id) != "sex_do_component_censored":
        raise ValueError("The last true branch does not enter the censored component")
    patched = bytearray(original)
    changes = []
    for export_index, true_link, false_link, offset in conditions:
        if true_link == false_link:
            raise ValueError("Scene already routes the branches together")
        struct.pack_into("<I", patched, offset, false_link)
        export = exports[export_index]
        crc = zlib.crc32(patched[export["offset"]:export["offset"] + export["size"]])
        struct.pack_into("<I", patched, export["entry"] + 20, crc)
        changes.append((export_index + 1, true_link, false_link))
    exports_at, exports_count, _ = table(patched, 4)
    struct.pack_into("<I", patched, 40 + 4 * 12 + 8,
                     zlib.crc32(patched[exports_at:exports_at + exports_count * 24]))
    struct.pack_into("<I", patched, 32, 0xDEADBEEF)
    struct.pack_into("<I", patched, 32, zlib.crc32(patched[:160]))
    parse(patched)  # Check every export and table CRC after the edit.
    return bytes(patched), changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write validated workspace scene checkouts")
    parser.add_argument("--verify", action="store_true", help="Validate patched workspace scene checkouts")
    args = parser.parse_args()
    if args.apply and args.verify:
        parser.error("Choose --apply or --verify")
    for name in SCENES:
        relative = SCENE_DIR / name
        source = REDKIT_DEPOT / relative
        checkout = PROJECT / "depot" / relative
        original = source.read_bytes()
        patched, changes = patch_scene(original)
        digest = hashlib.sha256(original).hexdigest()
        if not checkout.is_file():
            raise ValueError(f"Checkout is absent: {checkout}")
        current = checkout.read_bytes()
        if args.verify:
            from route_naked_appearances import patch as patch_naked
            fully_patched, appearance_changes = patch_naked(patched)
            if current != fully_patched:
                raise ValueError(f"Patched checkout does not match expected bytes: {checkout}")
            print(f"verified: {name}: {len(changes)} conditions, "
                  f"{len(appearance_changes)} appearance overrides, {len(current)} bytes")
            continue
        if hashlib.sha256(current).hexdigest() != digest:
            raise ValueError(f"Checkout differs from REDkit source: {checkout}")
        if args.apply:
            temporary = checkout.with_name(checkout.name + ".tmp")
            with temporary.open("xb") as output:
                output.write(patched)
            os.replace(temporary, checkout)
        mode = "patched" if args.apply else "ready"
        print(f"{mode}: {name}: " + ", ".join(
            f"condition #{idx} {before}->{after}" for idx, before, after in changes
        ))


if __name__ == "__main__":
    main()
