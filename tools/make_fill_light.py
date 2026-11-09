"""Make the close-up fill light: a copy of a stock cutscene point light with our values.

  python3 -I tools/make_fill_light.py src.w2ent out.w2ent brightness radius attenuation

src = fx/cutscenes/novigrad/cs103_baron_digs_grave/cs103_single_lightning.w2ent (REDkit
depot, uncooked): a bare CEntity with one CPointLightComponent and no mesh. Its light sits
50 m up, is off (brightness 0), reaches 150 m and flickers, because an fx flashes it for a
lightning strike. Every value is patched in place (same sizes), in the template and in the
entity copy inside flatCompiledData, which is what the game spawns from. Colour stays at
the default white so both skins get the same neutral light.
"""
import struct, sys
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "work", "scratch", "bones"))
from cr2w import CR2W


def patch(d, base, vals):
    c = CR2W(bytes(d[base:]))
    n = 0
    for e in c.exports:
        if c.names[e[0]] != "CPointLightComponent":
            continue
        pr, _ = c.props(e[4] + 1, e[4] + e[3])
        for name, typ, o, sz, _ in pr:
            o += base
            if name in vals:
                assert typ == "Float" and sz == 4
                struct.pack_into("<f", d, o, vals[name]); n += 1
            elif name == "transform":
                # EngineTransform: flags byte (1 = position only), then x, y, z.
                assert d[o] == 1 and sz == 13, (d[o], sz)
                struct.pack_into("<3f", d, o + 1, 0, 0, 0); n += 1
            elif name == "lightFlickering":
                sub, _ = c.props(o - base + 1, o - base + sz)
                for sn, st, so, ssz, _ in sub:
                    if sn == "flickerStrength":
                        struct.pack_into("<f", d, so + base, 0.0); n += 1
    return n


def main():
    src, out, b, r, a = sys.argv[1:6]
    vals = {"brightness": float(b), "radius": float(r), "attenuation": float(a)}
    d = bytearray(open(src, "rb").read())
    k = d.find(b"CR2W", 8)
    n0, n1 = patch(d, 0, vals), patch(d, k, vals)
    assert n0 == n1 == 5, (n0, n1)
    open(out, "wb").write(d)
    print("wrote", out, "patched", n0, n1)


if __name__ == "__main__":
    main()
