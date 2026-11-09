"""Rebuild a W3 CR2W file from its parts so names, imports and exports can be appended.

  f = Cr2w(data); f.name("X"); f.imp(path, cls); f.add_export(cls, parent, chunk); f.bytes()
Keeps the header fields and the properties table of the source; regenerates the string
table (names first, then import paths, as the game files lay it out), name hashes,
offsets and CRCs. Embedded files and internal buffers are not supported.
"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work", "scratch", "bones"))
from cr2w import CR2W
from rigbones import fnv1a32, crc

class Cr2w:
    def __init__(self, data):
        c = self.c = CR2W(data)
        assert all(t[1] == 0 for t in c.tables[5:]), "buffers/embedded not supported"
        self.names = list(c.names)
        no, nn, _ = c.tables[1]
        self.hashes = [struct.unpack_from("<II", c.d, no + 8 * i)[1] for i in range(nn)]
        io_, ic, _ = c.tables[2]
        self.imports = []
        for i in range(ic):
            so, cls, fl = struct.unpack_from("<IHH", c.d, io_ + 8 * i)
            self.imports.append([c.s(so), cls, fl])
        po, pc, _ = c.tables[3]
        self.props = bytes(c.d[po:po + 16 * pc])
        self.exports = [[e[0], e[1], e[2], bytes(c.d[e[4]:e[4] + e[3]]), e[6]] for e in c.exports]
    def name(self, n):
        if n not in self.names:
            self.names.append(n); self.hashes.append(fnv1a32(n.encode("latin-1")))
        return self.names.index(n)
    def imp(self, path, cls, flags=0):
        self.imports.append([path, self.name(cls), flags]); return -len(self.imports)
    def add_export(self, cls, parent, chunk):
        self.exports.append([self.name(cls), 0, parent, chunk, None]); return len(self.exports)
    def bytes(self):
        c = self.c
        strings = bytearray(); soff = {}
        def put(s):
            if s not in soff:
                soff[s] = len(strings); strings.extend(s.encode("latin-1") + b"\0")
            return soff[s]
        for n in self.names: put(n)
        names_tab = b"".join(struct.pack("<II", put(n), h) for n, h in zip(self.names, self.hashes))
        imports = b"".join(struct.pack("<IHH", put(p), cls, fl) for p, cls, fl in self.imports)
        pos = 160 + len(strings)
        names_off = pos; pos += len(names_tab)
        imp_off = pos if self.imports else 0; pos += len(imports)
        props_off = pos; pos += len(self.props)
        exp_off = pos; pos += 24 * len(self.exports)
        data = b""; exports = b""
        for cls, fl, parent, chunk, ocrc in self.exports:
            same = ocrc is not None and any(chunk == bytes(c.d[e[4]:e[4] + e[3]]) for e in c.exports if e[6] == ocrc)
            exports += struct.pack("<HHIIIII", cls, fl, parent, len(chunk), pos + len(data), 0, ocrc if same else crc(chunk))
            data += chunk
        fsize = pos + len(data)
        tables = [(160, len(strings), crc(bytes(strings))), (names_off, len(self.names), crc(names_tab)),
                  (imp_off, len(self.imports), crc(imports) if self.imports else 0),
                  (props_off, len(self.props) // 16, crc(self.props)), (exp_off, len(self.exports), crc(exports))] + [(0, 0, 0)] * 5
        def header(h):
            return b"CR2W" + struct.pack("<IIQIIIII", c.version, c.flags, c.ts, c.build, fsize, fsize, h, c.nchunks) + \
                b"".join(struct.pack("<III", *t) for t in tables)
        return header(crc(header(0xDEADBEEF))) + bytes(strings) + names_tab + imports + self.props + exports + data

if __name__ == "__main__":
    d = open(sys.argv[1], "rb").read()
    out = Cr2w(d).bytes()
    print("identical:", out == d, len(out), len(d))
    if out != d:
        diffs = [i for i in range(min(len(out), len(d))) if out[i] != d[i]]
        print("ndiff", len(diffs), diffs[:20])
