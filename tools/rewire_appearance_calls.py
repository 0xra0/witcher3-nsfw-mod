#!/usr/bin/env python3
"""Move each brothel scene's AppearanceChange calls to the scene's start and end.

Cutscene actorOverrides do not restyle the live brothel NPC; only the scene's
two AppearanceChange_scene script blocks do. Retail runs `_naked` just before
sex_do_component and `_panties` just after it, so every pre and after section
shows lingerie. This rewires existing link pointers so the flow becomes

    Input -> NAKED -> (original start ... pre ... main ... after) -> PANTIES -> Output

No element is added or resized; only `nextLinkElement` pointers change.
check_flow() walks every path and fails unless each reachable cutscene section
runs while the partner's last applied appearance is `_naked`.
"""

from __future__ import annotations

import struct
import zlib

from route_regular_scenes import parse, prop_u32, section_name, table, u32

# Elements the scene player walks through. Other ptr targets (scene elements,
# dialogsets, variants) are not flow nodes.
FLOW_CLASSES = {
    "CStorySceneInput", "CStorySceneOutput", "CStorySceneLinkElement",
    "CStorySceneScript", "CStorySceneFlowCondition", "CStorySceneRandomizer",
    "CStorySceneCutsceneSection", "CStorySceneSection",
}


def _appearance_call(data: bytes, names: list[str], export: dict) -> str | None:
    """Return 'naked'/'panties' for an AppearanceChange_scene block, else None."""
    if export["class"] != "CStorySceneScript":
        return None
    _, offset, _ = export["props"]["functionName"]
    if names[struct.unpack_from("<H", data, offset)[0]] != "AppearanceChange_scene":
        return None
    blob = data[export["offset"]:export["offset"] + export["size"]]
    kinds = {kind for kind in ("naked", "panties")
             if any(n.endswith("_" + kind) and struct.pack("<H", i) in blob
                    for i, n in enumerate(names))}
    if len(kinds) != 1:
        raise ValueError(f"Ambiguous AppearanceChange arguments: {kinds}")
    return kinds.pop()


def _edges(data: bytes, exports: list[dict], index: int) -> list[int]:
    """Flow successors of export `index` (1-based), excluding back-references."""
    out = []
    for prop, (ptype, offset, size) in exports[index - 1]["props"].items():
        if prop == "linkedElements":
            continue
        if ptype.startswith("ptr:") and size == 4:
            targets = [u32(data, offset)]
        elif ptype.startswith("array:") and ",ptr:" in ptype:
            count = u32(data, offset)
            targets = [u32(data, offset + 4 + 4 * k) for k in range(count)]
        else:
            continue
        out += [t for t in targets if 0 < t <= len(exports)
                and exports[t - 1]["class"] in FLOW_CLASSES]
    return out


def _set_ptr(buf: bytearray, export: dict, prop: str, target: int) -> None:
    _, offset = prop_u32(buf, export, prop)
    struct.pack_into("<I", buf, offset, target)


def _refresh_crcs(buf: bytearray, exports: list[dict]) -> None:
    for export in exports:
        crc = zlib.crc32(buf[export["offset"]:export["offset"] + export["size"]])
        struct.pack_into("<I", buf, export["entry"] + 20, crc)
    exports_at, exports_count, _ = table(buf, 4)
    struct.pack_into("<I", buf, 40 + 4 * 12 + 8,
                     zlib.crc32(buf[exports_at:exports_at + exports_count * 24]))
    struct.pack_into("<I", buf, 32,
                     zlib.crc32(buf[:32] + b"\xef\xbe\xad\xde" + buf[36:160]))


def rewire(data: bytes, only_main: bool = False) -> tuple[bytes, list[str]]:
    """only_main (testing): Input -> NAKED -> sex_do_component -> PANTIES -> Output; every
    lead-in and after section becomes unreachable."""
    names, exports = parse(data)
    by_class = lambda c: [i for i, e in enumerate(exports, 1) if e["class"] == c]
    calls = {i: _appearance_call(data, names, e) for i, e in enumerate(exports, 1)}
    naked = [i for i, k in calls.items() if k == "naked"]
    panties = [i for i, k in calls.items() if k == "panties"]
    inputs, outputs = by_class("CStorySceneInput"), by_class("CStorySceneOutput")
    if len(naked) != 1 or len(panties) != 1 or len(inputs) != 1 or len(outputs) != 1:
        raise ValueError(f"Unexpected shape: naked={naked} panties={panties} "
                         f"inputs={inputs} outputs={outputs}")
    naked, panties, entry, exit_ = naked[0], panties[0], inputs[0], outputs[0]

    def nxt(i: int) -> int:
        return prop_u32(data, exports[i - 1], "nextLinkElement")[0]

    def into(target: int) -> list[int]:
        return [i for i, e in enumerate(exports, 1)
                if "nextLinkElement" in e["props"] and nxt(i) == target]

    start, main, after = nxt(entry), nxt(naked), nxt(panties)
    if exports[main - 1]["class"] != "CStorySceneCutsceneSection" \
            or section_name(data, exports[main - 1]) != "sex_do_component":
        raise ValueError("NAKED call does not lead into sex_do_component")
    to_naked, to_panties = into(naked), into(panties)
    to_exit = [i for i in into(exit_) if i != panties]
    if len(to_naked) != 1 or len(to_panties) != 1 or not to_exit:
        raise ValueError(f"Unexpected links: ->naked {to_naked} ->panties {to_panties} "
                         f"->output {to_exit}")
    for i, e in enumerate(exports, 1):  # Output must only be entered via nextLinkElement.
        for prop in ("trueLink", "falseLink"):
            if prop in e["props"] and prop_u32(data, e, prop)[0] in (exit_, naked, panties):
                raise ValueError(f"Export {i} {prop} targets a rewired element")

    buf = bytearray(data)
    log = []

    def link(src: int, target: int, why: str) -> None:
        _set_ptr(buf, exports[src - 1], "nextLinkElement", target)
        log.append(f"#{src}.next -> #{target} ({why})")

    link(entry, naked, "start naked")
    if only_main:
        link(naked, main, "test build: straight into sex_do_component")
    else:
        link(naked, start, "then the original opening")
        link(to_naked[0], main, "regular branch straight into sex_do_component")
        link(to_panties[0], after, "keep naked through the after sections")
        for src in to_exit:
            link(src, panties, "restore the brothel look on exit")
    link(panties, exit_, "then leave the scene")
    _refresh_crcs(buf, exports)
    result = bytes(buf)
    if len(result) != len(data):
        raise AssertionError("size changed")
    parse(result)  # Re-validates every table and export CRC.
    check_flow(result)
    return result, log


def check_flow(data: bytes) -> list[str]:
    """Walk all paths; every reachable cutscene section must run while naked."""
    names, exports = parse(data)
    entry = next(i for i, e in enumerate(exports, 1) if e["class"] == "CStorySceneInput")
    seen, stack, sections = set(), [(entry, None)], set()
    while stack:
        node, state = stack.pop()
        if (node, state) in seen:
            continue
        seen.add((node, state))
        export = exports[node - 1]
        state = _appearance_call(data, names, export) or state
        if export["class"] == "CStorySceneCutsceneSection":
            name = section_name(data, export)
            sections.add(name)
            if state != "naked":
                raise ValueError(f"{name} is reachable with appearance {state!r}")
            if name == "sex_do_component_censored":
                raise ValueError("Censored component is still reachable")
        if export["class"] == "CStorySceneOutput" and state != "panties":
            raise ValueError(f"Scene exits with appearance {state!r}")
        stack += [(t, state) for t in _edges(data, exports, node)]
    return sorted(sections)
