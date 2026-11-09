"""Write an edited top mip back into one DXT1 texture of a W3 texture.cache.

  python3 -I tools/patch_texcache.py src.cache "depot\\path.xbm" edited.png out.cache

edited.png is the full-size top mip (e.g. a texcache_dds.py dump decoded and painted on).
Only the 4x4 blocks whose texels changed are re-encoded (ImageMagick's DXT1 encoder), in
every whole-mip chunk from the box-downsampled edit; all other blocks keep their original
bytes. The packed tail chunk (mips a few texels wide) is left as it was. Output is a
single-entry cache like tint_texcache.py's, ready for merge_texcache.py.
"""
import os, struct, subprocess, sys, zlib
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tint_texcache import read_entry, write_entry


def rgb565(c):
    return np.stack([(c >> 11) & 31, (c >> 5) & 63, c & 31], -1) * (255 / np.array([31, 63, 31]))


def decode_dxt1(raw, w, h):
    b = np.frombuffer(raw, dtype='<u4').reshape(-1, 2)
    c0, c1, idx = b[:, 0] & 0xffff, b[:, 0] >> 16, b[:, 1]
    p0, p1 = rgb565(c0), rgb565(c1)
    four = (c0 > c1)[:, None]
    pal = np.stack([p0, p1, np.where(four, (2 * p0 + p1) / 3, (p0 + p1) / 2),
                    np.where(four, (p0 + 2 * p1) / 3, 0)], 1)               # (N, 4, 3)
    sel = (idx[:, None] >> (2 * np.arange(16))) & 3                          # (N, 16)
    tex = np.take_along_axis(pal, sel[:, :, None], 1)                        # (N, 16, 3)
    bw, bh = (w + 3) // 4, (h + 3) // 4
    return tex.reshape(bh, bw, 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 3)[:h, :w]


def encode_dxt1(img, tmp):
    """DXT1 blocks (bh, bw, 8 bytes) for an RGB image whose sides are multiples of 4."""
    Image.fromarray(np.clip(np.rint(img), 0, 255).astype(np.uint8)).save(tmp + '.png')
    subprocess.run(['magick', tmp + '.png', '-alpha', 'off', '-define', 'dds:compression=dxt1',
                    '-define', 'dds:mipmaps=0', tmp + '.dds'], check=True)
    raw = open(tmp + '.dds', 'rb').read()[128:]
    h, w = img.shape[:2]
    return np.frombuffer(raw[:w * h // 2], dtype=np.uint8).reshape(h // 4, w // 4, 8)


def main():
    src, name, edited, out = sys.argv[1:5]
    tmp = os.path.splitext(out)[0] + '_enc'
    v, data, ver = read_entry(src, name)
    W, H = v[6], v[7]
    chunks, pos = [], 0
    while pos < len(data) - 9:
        zs, us, mi = struct.unpack_from('<IIB', data, pos)
        if zs == 0:
            break
        chunks.append((zlib.decompress(data[pos + 9:pos + 9 + zs]), mi))
        pos += 9 + zs
    new = np.asarray(Image.open(edited).convert('RGB')).astype(float)
    assert new.shape[:2] == (H, W), new.shape
    changed = np.abs(new - decode_dxt1(chunks[0][0], W, H)).max(2) > 8
    print('changed texels', int(changed.sum()))
    body, mips = bytearray(), []
    for raw, mi in chunks:
        lv = next((k for k in range(16) if len(raw) == max(1, ((W >> k) + 3) // 4) * max(1, ((H >> k) + 3) // 4) * 8), None)
        if lv is not None and (W >> lv) >= 4 and changed.any():
            s = 1 << lv
            w, h = W >> lv, H >> lv
            down = new.reshape(h, s, w, s, 3).mean((1, 3))
            # a block changes when any top-mip texel under it changed
            cb = changed.reshape(h // 4, 4 * s, w // 4, 4 * s).any((1, 3))
            ys, xs = np.where(cb)
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            enc = encode_dxt1(down[4 * y0:4 * y1, 4 * x0:4 * x1], tmp)
            blk = np.frombuffer(raw, dtype=np.uint8).reshape(h // 4, w // 4, 8).copy()
            blk[y0:y1, x0:x1] = np.where(cb[y0:y1, x0:x1, None], enc, blk[y0:y1, x0:x1])
            raw = blk.tobytes()
            print('mip %d: %d blocks re-encoded' % (lv, int(cb.sum())))
        z = zlib.compress(raw, 9)
        if body:
            mips.append(len(body))
        body += struct.pack('<IIB', len(z), len(raw), mi) + z
    for ext in ('.png', '.dds'):
        if os.path.exists(tmp + ext):
            os.remove(tmp + ext)
    write_entry(out, name, v, ver, body, mips)


if __name__ == '__main__':
    main()
