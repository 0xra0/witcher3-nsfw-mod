"""Write the uncooked .w3dyng that gives Geralt's penis chain (penis_01..04) dangle physics.

  python3 tools/penis_dyng.py man_base.json out.w3dyng [hard|semi|soft]
man_base.json: work/scratch/bones/dump.py output of the live (penis) man_base.w2rig.
Every rig bone but Root and the motion/IK helpers becomes a pinned node (distance 0) so the body mesh can skin to
the dangle skeleton; penis_02..04 and a tip null swing within growing distances of their
animated pose, pulled back by the preset stiffness. Links keep the segment lengths.
The CR2W container is REDkit's uncooked eight necklace dyng; wcc_lite adds the skeleton.
"""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dyngio import decode, encode, mat

TEMPLATE = "/mnt/sata/Games/The Witcher 3 REDkit/r4data/characters/models/secondary_npc/eight/model/dyng_i_01_ma__eight.w3dyng"
CHAIN = ["penis_01", "penis_02", "penis_03", "penis_04", "penis_05_null"]
# per chain node: (mass, stiffness, distance m). penis_01 stays pinned to the pelvis.
PRESETS = {
    "hard": [(1, 0, 0), (1.0, 0.6, 0.006), (1.0, 0.6, 0.012), (1.0, 0.6, 0.018), (1.0, 0.6, 0.024)],
    "semi": [(1, 0, 0), (1.0, 0.15, 0.02), (1.0, 0.15, 0.04), (1.0, 0.15, 0.06), (1.0, 0.15, 0.08)],
    "soft": [(1, 0, 0), (1.0, 0.0, 0.03), (1.0, 0.0, 0.06), (1.0, 0.0, 0.09), (1.0, 0.0, 0.12)],
}

def local_rows(pos, q):
    """Parent-local transform as the dyng stores it: rows are the rotated basis vectors."""
    x, y, z, w = q
    R = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    rows = [[R[0][r], R[1][r], R[2][r], 0.0] for r in range(3)]
    return rows + [[pos[0], pos[1], pos[2], 1.0]]

def build(rig, preset):
    names, parents, tf = rig["names"], rig["parents"], rig["tf"]
    nodes = []  # (name, parent, rows)
    for i, n in enumerate(names):
        if n in ("Root", "Trajectory", "Reference") or n.startswith("IK_"):
            continue
        t = tf[i]
        nodes.append((n, names[parents[i]], local_rows(t[0:3], t[4:8])))
    # tip null one segment past penis_04, same parent-local offset as the segments before it
    seg = tf[names.index("penis_04")][0:3]
    nodes.append(("penis_05_null", "penis_04", local_rows(seg, (0, 0, 0, 1))))
    idx = {n: k for k, (n, _, _) in enumerate(nodes)}
    N = len(nodes)
    mass, stiff, dist = [1.0] * N, [0.0] * N, [0.0] * N
    for n, (m, s, d) in zip(CHAIN, PRESETS[preset]):
        k = idx[n]; mass[k], stiff[k], dist[k] = float(m), float(s), float(d)
    la, lb, ll = [], [], []
    for a, b in zip(CHAIN, CHAIN[1:]):
        r = nodes[idx[b]][2][3]
        la.append(idx[a]); lb.append(idx[b]); ll.append(math.sqrt(r[0] ** 2 + r[1] ** 2 + r[2] ** 2))
    ident = [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]
    names_ = [n for n, _, _ in nodes]
    return {
        "nodeNames": names_, "nodeParents": [p for _, p, _ in nodes],
        "nodeMasses": mass, "nodeStifnesses": stiff, "nodeDistances": dist,
        "nodeTransforms": [mat(r) for _, _, r in nodes],
        "linkTypes": [0] * len(la), "linkLengths": ll, "linkAs": la, "linkBs": lb,
        "collisionParents": names_, "collisionRadiuses": [0.0] * N,
        "collisionHeights": [0.006 if n in CHAIN else 0.0 for n in names_],
        "collisionTransforms": [mat(ident) for _ in nodes],
    }

if __name__ == "__main__":
    rig = json.load(open(sys.argv[1]))
    preset = sys.argv[3] if len(sys.argv) > 3 else "semi"
    c, props, tail = decode(TEMPLATE)
    new = build(rig, preset)
    props = [(n, t, new.get(n, v)) for n, t, v in props]
    open(sys.argv[2], "wb").write(encode(c, props, tail))
    print(preset, len(new["nodeNames"]), "nodes, links", list(zip(new["linkAs"], new["linkBs"], [round(x, 4) for x in new["linkLengths"]])))
