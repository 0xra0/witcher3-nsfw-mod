#!/usr/bin/env python3
"""Print a cooked w2scene's flow graph: sections, script calls and their appearance arguments.

Usage: scene_flow.py <scene.w2scene>...
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from route_regular_scenes import parse, prop_u32, section_name

LINK_PROPS = ("nextLinkElement", "trueLink", "falseLink")


def appearance_args(data: bytes, names: list[str], export: dict) -> list[str]:
    blob = data[export["offset"]:export["offset"] + export["size"]]
    return [n for i, n in enumerate(names)
            if n.endswith(("_naked", "_panties")) and struct.pack("<H", i) in blob]


def describe(data: bytes, names: list[str], exports: list[dict], index: int) -> str:
    export = exports[index - 1]
    cls = export["class"]
    if cls == "CStorySceneCutsceneSection":
        return f"{index}:CS[{section_name(data, export)}]"
    if cls == "CStorySceneScript":
        _, offset, _ = export["props"]["functionName"]
        function = names[struct.unpack_from("<H", data, offset)[0]]
        args = appearance_args(data, names, export)
        return f"{index}:SCRIPT[{function}{' ' + ','.join(args) if args else ''}]"
    return f"{index}:{cls.replace('CStoryScene', '')}"


def flow(data: bytes) -> list[str]:
    names, exports = parse(data)
    lines = []
    for index, export in enumerate(exports, 1):
        links = []
        for prop in LINK_PROPS:
            if prop in export["props"]:
                target, _ = prop_u32(data, export, prop)
                links.append(f"{prop}->{describe(data, names, exports, target) if target else 0}")
        if links:
            lines.append(f"{describe(data, names, exports, index)}  {' | '.join(links)}")
    return lines


def main() -> None:
    for name in sys.argv[1:]:
        print(f"== {Path(name).name}")
        print("\n".join(flow(Path(name).read_bytes())))


if __name__ == "__main__":
    main()
