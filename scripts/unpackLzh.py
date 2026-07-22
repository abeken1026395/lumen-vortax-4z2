# -*- coding: utf-8 -*-
"""Pure-Python LHA -lh5- decoder (validated byte-exact on k260710).
Provides load_lzh(path) -> (raw_bytes, meta) with size + CRC-16 integrity check.
"""
import struct

DICBIT = 13
THRESHOLD = 3
MAXMATCH = 256
NC = 255 + MAXMATCH + 2 - THRESHOLD   # 510
NP = DICBIT + 1                        # 14
NT = 19
CBIT = 9
PBIT = 4
TBIT = 5


class CorruptError(Exception):
    pass


class BitIn:
    __slots__ = ("d", "p", "buf", "n")

    def __init__(self, data):
        self.d = data
        self.p = 0
        self.buf = 0
        self.n = 0

    def getbits(self, k):
        if k == 0:
            return 0
        while self.n < k:
            b = self.d[self.p] if self.p < len(self.d) else 0
            self.p += 1
            self.buf = (self.buf << 8) | b
            self.n += 8
        self.n -= k
        return (self.buf >> self.n) & ((1 << k) - 1)


class Huff:
    __slots__ = ("single", "tab")

    def __init__(self, lengths, single=None):
        self.single = single
        if single is not None:
            return
        count = [0] * 17
        for l in lengths:
            if l:
                count[l] += 1
        code = 0
        nxt = [0] * 17
        for l in range(1, 17):
            code = (code + count[l - 1]) << 1
            nxt[l] = code
        tab = {}
        for sym, l in enumerate(lengths):
            if l:
                tab[(l, nxt[l])] = sym
                nxt[l] += 1
        self.tab = tab

    def decode(self, br):
        if self.single is not None:
            return self.single
        code = 0
        length = 0
        tab = self.tab
        while True:
            code = (code << 1) | br.getbits(1)
            length += 1
            s = tab.get((length, code))
            if s is not None:
                return s
            if length > 16:
                raise CorruptError("bad huffman code")


def _read_pt_len(br, nn, nbit, i_special):
    n = br.getbits(nbit)
    if n == 0:
        return Huff(None, single=br.getbits(nbit))
    lens = [0] * nn
    i = 0
    while i < n:
        c = br.getbits(3)
        if c == 7:
            while br.getbits(1) == 1:
                c += 1
        lens[i] = c
        i += 1
        if i == i_special:
            for _ in range(br.getbits(2)):
                lens[i] = 0
                i += 1
    return Huff(lens)


def _read_c_len(br, temp):
    n = br.getbits(CBIT)
    if n == 0:
        return Huff(None, single=br.getbits(CBIT))
    lens = [0] * NC
    i = 0
    while i < n:
        c = temp.decode(br)
        if c <= 2:
            if c == 0:
                run = 1
            elif c == 1:
                run = br.getbits(4) + 3
            else:
                run = br.getbits(CBIT) + 20
            for _ in range(run):
                lens[i] = 0
                i += 1
        else:
            lens[i] = c - 2
            i += 1
    return Huff(lens)


def decompress(comp, outsize):
    br = BitIn(comp)
    out = bytearray()
    blocksize = 0
    c_huff = p_huff = None
    while len(out) < outsize:
        if blocksize == 0:
            blocksize = br.getbits(16)
            temp = _read_pt_len(br, NT, TBIT, 3)
            c_huff = _read_c_len(br, temp)
            p_huff = _read_pt_len(br, NP, PBIT, -1)
        blocksize -= 1
        c = c_huff.decode(br)
        if c < 256:
            out.append(c)
        else:
            length = c - 256 + THRESHOLD
            p = p_huff.decode(br)
            if p != 0:
                p = (1 << (p - 1)) + br.getbits(p - 1)
            start = len(out) - p - 1
            if start < 0:
                raise CorruptError("bad match position")
            for k in range(length):
                out.append(out[start + k])
    return bytes(out[:outsize])


def crc16(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def load_lzh(path):
    """Return (raw_bytes, meta). Raises CorruptError on size/CRC mismatch.
    Handles level-0 header (mbrace K files)."""
    data = open(path, "rb").read()
    if len(data) < 24:
        raise CorruptError("file too small")
    hsize = data[0]
    method = data[2:7].decode("ascii", "replace")
    if method != "-lh5-":
        raise CorruptError("unexpected method %r" % method)
    compsize = struct.unpack("<I", data[7:11])[0]
    origsize = struct.unpack("<I", data[11:15])[0]
    level = data[20]
    fnlen = data[21]
    fname = data[22:22 + fnlen].decode("shift_jis", "replace")
    hdr_crc = struct.unpack("<H", data[22 + fnlen:24 + fnlen])[0]
    dataoff = 2 + hsize
    comp = data[dataoff:dataoff + compsize]
    raw = decompress(comp, origsize)
    if len(raw) != origsize:
        raise CorruptError("size mismatch %d != %d" % (len(raw), origsize))
    calc = crc16(raw)
    if calc != hdr_crc:
        raise CorruptError("CRC mismatch calc=%04X hdr=%04X" % (calc, hdr_crc))
    meta = dict(method=method, level=level, compsize=compsize,
                origsize=origsize, fname=fname, crc=hdr_crc)
    return raw, meta


if __name__ == "__main__":
    import sys
    raw, meta = load_lzh(sys.argv[1])
    print("OK", meta, "bytes=%d" % len(raw))
