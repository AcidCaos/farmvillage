"""Minimal AVM2 (ABC) reader/disassembler for read-only client inspection.

Read-only. Standard library only. See macOS/Documentation/AGENT_PLAYBOOK.md.

Usage (REGEX is a Python regular expression):
  python3 -I abcdis.py SWF find REGEX     -> list methods named like Package:Class.method
  python3 -I abcdis.py SWF dis REGEX      -> disassemble matching methods (debugline = source line)
  python3 -I abcdis.py SWF strings REGEX  -> methods whose code mentions a matching string/name

The first run parses the SWF and writes a cache next to it (SWF.abc.pickle).
Work on a COPY of the client (e.g. in a scratch folder), never the repo's embeds/.
Get the exact client the server serves with:
  curl -o FarmGame.served.swf http://127.0.0.1:<port>/embeds/Flash/v855097-855094/FarmGame.swf
"""
import re
import struct
import sys
import zlib
import pickle
import os


def swf_tags(path):
    data = open(path, "rb").read()
    sig = data[:3]
    if sig == b"CWS":
        body = zlib.decompress(data[8:])
    elif sig == b"FWS":
        body = data[8:]
    else:
        raise SystemExit("unsupported swf " + repr(sig))
    nbits = body[0] >> 3
    pos = (5 + 4 * nbits + 7) // 8 + 4
    while pos < len(body):
        code_len = struct.unpack_from("<H", body, pos)[0]
        pos += 2
        code, length = code_len >> 6, code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", body, pos)[0]
            pos += 4
        yield code, body[pos:pos + length]
        pos += length
        if code == 0:
            break


class R:
    def __init__(self, b, p=0):
        self.b, self.p = b, p

    def u8(self):
        v = self.b[self.p]; self.p += 1; return v

    def u16(self):
        v = struct.unpack_from("<H", self.b, self.p)[0]; self.p += 2; return v

    def s24(self):
        v = int.from_bytes(self.b[self.p:self.p + 3], "little", signed=True); self.p += 3; return v

    def u30(self):
        r = 0; shift = 0
        for _ in range(5):
            x = self.b[self.p]; self.p += 1
            r |= (x & 0x7F) << shift
            if not x & 0x80:
                break
            shift += 7
        return r

    def s32(self):
        r = self.u30()
        return r - (1 << 32) if r & 0x80000000 else r

    def d64(self):
        v = struct.unpack_from("<d", self.b, self.p)[0]; self.p += 8; return v


class ABC:
    def __init__(self, b):
        r = R(b)
        r.u16(); r.u16()
        n = r.u30(); self.ints = [0] + [r.s32() for _ in range(max(0, n - 1))]
        n = r.u30(); self.uints = [0] + [r.u30() for _ in range(max(0, n - 1))]
        n = r.u30(); self.doubles = [0.0] + [r.d64() for _ in range(max(0, n - 1))]
        n = r.u30(); self.strings = [""]
        for _ in range(max(0, n - 1)):
            ln = r.u30(); self.strings.append(b[r.p:r.p + ln].decode("utf8", "replace")); r.p += ln
        n = r.u30(); self.ns = [("", "*")]
        for _ in range(max(0, n - 1)):
            kind = r.u8(); self.ns.append((kind, self.strings[r.u30()]))
        n = r.u30(); self.nssets = [[]]
        for _ in range(max(0, n - 1)):
            c = r.u30(); self.nssets.append([r.u30() for _ in range(c)])
        n = r.u30(); self.mn = [None]
        for _ in range(max(0, n - 1)):
            k = r.u8()
            if k in (0x07, 0x0D):
                self.mn.append(("Q", r.u30(), r.u30()))
            elif k in (0x0F, 0x10):
                self.mn.append(("RTQ", r.u30()))
            elif k in (0x11, 0x12):
                self.mn.append(("RTQL",))
            elif k in (0x09, 0x0E):
                self.mn.append(("M", r.u30(), r.u30()))
            elif k in (0x1B, 0x1C):
                self.mn.append(("ML", r.u30()))
            elif k == 0x1D:
                base = r.u30(); c = r.u30(); self.mn.append(("TN", base, [r.u30() for _ in range(c)]))
            else:
                raise ValueError("mn kind %x" % k)
        n = r.u30(); self.methods = []
        for _ in range(n):
            pc = r.u30(); r.u30(); [r.u30() for _ in range(pc)]
            name = r.u30(); flags = r.u8()
            if flags & 0x08:
                oc = r.u30()
                for _ in range(oc):
                    r.u30(); r.u8()
            if flags & 0x80:
                [r.u30() for _ in range(pc)]
            self.methods.append(self.strings[name])
        n = r.u30()
        for _ in range(n):
            r.u30(); c = r.u30()
            for _ in range(c):
                r.u30(); r.u30()
        n = r.u30(); self.instances = []
        for _ in range(n):
            name = r.u30(); r.u30(); flags = r.u8()
            if flags & 0x08:
                r.u30()
            ic = r.u30(); [r.u30() for _ in range(ic)]
            iinit = r.u30()
            traits = self._traits(r)
            self.instances.append((name, iinit, traits))
        self.classes = []
        for _ in range(n):
            cinit = r.u30(); self.classes.append((cinit, self._traits(r)))
        n = r.u30()
        for _ in range(n):
            r.u30(); self._traits(r)
        n = r.u30(); self.bodies = {}
        for _ in range(n):
            m = r.u30(); r.u30(); r.u30(); r.u30(); r.u30()
            ln = r.u30(); code = b[r.p:r.p + ln]; r.p += ln
            ec = r.u30()
            for _ in range(ec):
                r.u30(); r.u30(); r.u30(); r.u30(); r.u30()
            self._traits(r)
            self.bodies[m] = code

    def _traits(self, r):
        out = []
        c = r.u30()
        for _ in range(c):
            name = r.u30(); kind = r.u8(); k = kind & 0x0F
            if k in (0, 6):
                r.u30(); r.u30(); vi = r.u30()
                if vi:
                    r.u8()
                out.append((name, "slot", None))
            elif k in (1, 2, 3):
                r.u30(); mi = r.u30(); out.append((name, {1: "m", 2: "get", 3: "set"}[k], mi))
            elif k in (4, 5):
                r.u30(); r.u30(); out.append((name, "cls", None))
            else:
                raise ValueError("trait kind")
            if kind & 0x40:
                mc = r.u30(); [r.u30() for _ in range(mc)]
        return out

    def mname(self, i):
        m = self.mn[i] if 0 <= i < len(self.mn) else None
        if not m:
            return "*"
        if m[0] == "Q":
            ns = self.ns[m[1]][1]
            return (ns + ":" if ns else "") + self.strings[m[2]]
        if m[0] == "M":
            return self.strings[m[1]]
        if m[0] == "RTQ":
            return self.strings[m[1]]
        if m[0] == "TN":
            return self.mname(m[1]) + ".<" + ",".join(self.mname(x) for x in m[2]) + ">"
        return "[late]"

    def short(self, i):
        m = self.mn[i] if 0 <= i < len(self.mn) else None
        if m and m[0] in ("Q", "M", "RTQ"):
            return self.strings[m[2] if m[0] == "Q" else m[1]]
        return self.mname(i)


# opcode -> (name, operand kinds). kinds: u=u30 index raw, m=multiname, s=string, i=int, d=double, b=byte, o=s24 offset, ms=multiname+argcount
OPS = {
    0x01: ("bkpt", ""), 0x02: ("nop", ""), 0x03: ("throw", ""), 0x04: ("getsuper", "m"), 0x05: ("setsuper", "m"),
    0x06: ("dxns", "s"), 0x07: ("dxnslate", ""), 0x08: ("kill", "u"), 0x09: ("label", ""),
    0x0C: ("ifnlt", "o"), 0x0D: ("ifnle", "o"), 0x0E: ("ifngt", "o"), 0x0F: ("ifnge", "o"), 0x10: ("jump", "o"),
    0x11: ("iftrue", "o"), 0x12: ("iffalse", "o"), 0x13: ("ifeq", "o"), 0x14: ("ifne", "o"), 0x15: ("iflt", "o"),
    0x16: ("ifle", "o"), 0x17: ("ifgt", "o"), 0x18: ("ifge", "o"), 0x19: ("ifstricteq", "o"), 0x1A: ("ifstrictne", "o"),
    0x1B: ("lookupswitch", "X"), 0x1C: ("pushwith", ""), 0x1D: ("popscope", ""), 0x1E: ("nextname", ""),
    0x1F: ("hasnext", ""), 0x20: ("pushnull", ""), 0x21: ("pushundefined", ""), 0x23: ("nextvalue", ""),
    0x24: ("pushbyte", "b"), 0x25: ("pushshort", "u"), 0x26: ("pushtrue", ""), 0x27: ("pushfalse", ""),
    0x28: ("pushnan", ""), 0x29: ("pop", ""), 0x2A: ("dup", ""), 0x2B: ("swap", ""), 0x2C: ("pushstring", "s"),
    0x2D: ("pushint", "i"), 0x2E: ("pushuint", "u"), 0x2F: ("pushdouble", "d"), 0x30: ("pushscope", ""),
    0x31: ("pushnamespace", "u"), 0x32: ("hasnext2", "uu"), 0x40: ("newfunction", "u"), 0x41: ("call", "u"),
    0x42: ("construct", "u"), 0x43: ("callmethod", "uu"), 0x44: ("callstatic", "uu"), 0x45: ("callsuper", "mu"),
    0x46: ("callproperty", "mu"), 0x47: ("returnvoid", ""), 0x48: ("returnvalue", ""), 0x49: ("constructsuper", "u"),
    0x4A: ("constructprop", "mu"), 0x4C: ("callproplex", "mu"), 0x4E: ("callsupervoid", "mu"),
    0x4F: ("callpropvoid", "mu"), 0x53: ("applytype", "u"), 0x55: ("newobject", "u"), 0x56: ("newarray", "u"),
    0x57: ("newactivation", ""), 0x58: ("newclass", "u"), 0x59: ("getdescendants", "m"), 0x5A: ("newcatch", "u"),
    0x5D: ("findpropstrict", "m"), 0x5E: ("findproperty", "m"), 0x5F: ("finddef", "m"), 0x60: ("getlex", "m"),
    0x61: ("setproperty", "m"), 0x62: ("getlocal", "u"), 0x63: ("setlocal", "u"), 0x64: ("getglobalscope", ""),
    0x65: ("getscopeobject", "b"), 0x66: ("getproperty", "m"), 0x68: ("initproperty", "m"), 0x6A: ("deleteproperty", "m"),
    0x6C: ("getslot", "u"), 0x6D: ("setslot", "u"), 0x6E: ("getglobalslot", "u"), 0x6F: ("setglobalslot", "u"),
    0x70: ("convert_s", ""), 0x71: ("esc_xelem", ""), 0x72: ("esc_xattr", ""), 0x73: ("convert_i", ""),
    0x74: ("convert_u", ""), 0x75: ("convert_d", ""), 0x76: ("convert_b", ""), 0x77: ("convert_o", ""),
    0x78: ("checkfilter", ""), 0x80: ("coerce", "m"), 0x81: ("coerce_b", ""), 0x82: ("coerce_a", ""),
    0x83: ("coerce_i", ""), 0x84: ("coerce_d", ""), 0x85: ("coerce_s", ""), 0x86: ("astype", "m"),
    0x87: ("astypelate", ""), 0x88: ("coerce_u", ""), 0x89: ("coerce_o", ""), 0x90: ("negate", ""),
    0x91: ("increment", ""), 0x92: ("inclocal", "u"), 0x93: ("decrement", ""), 0x94: ("declocal", "u"),
    0x95: ("typeof", ""), 0x96: ("not", ""), 0x97: ("bitnot", ""), 0xA0: ("add", ""), 0xA1: ("subtract", ""),
    0xA2: ("multiply", ""), 0xA3: ("divide", ""), 0xA4: ("modulo", ""), 0xA5: ("lshift", ""), 0xA6: ("rshift", ""),
    0xA7: ("urshift", ""), 0xA8: ("bitand", ""), 0xA9: ("bitor", ""), 0xAA: ("bitxor", ""), 0xAB: ("equals", ""),
    0xAC: ("strictequals", ""), 0xAD: ("lessthan", ""), 0xAE: ("lessequals", ""), 0xAF: ("greaterthan", ""),
    0xB0: ("greaterequals", ""), 0xB1: ("instanceof", ""), 0xB2: ("istype", "m"), 0xB3: ("istypelate", ""),
    0xB4: ("in", ""), 0xC0: ("increment_i", ""), 0xC1: ("decrement_i", ""), 0xC2: ("inclocal_i", "u"),
    0xC3: ("declocal_i", "u"), 0xC4: ("negate_i", ""), 0xC5: ("add_i", ""), 0xC6: ("subtract_i", ""),
    0xC7: ("multiply_i", ""), 0xD0: ("getlocal0", ""), 0xD1: ("getlocal1", ""), 0xD2: ("getlocal2", ""),
    0xD3: ("getlocal3", ""), 0xD4: ("setlocal0", ""), 0xD5: ("setlocal1", ""), 0xD6: ("setlocal2", ""),
    0xD7: ("setlocal3", ""), 0xEF: ("debug", "bubu"), 0xF0: ("debugline", "u"), 0xF1: ("debugfile", "s"),
    0x35: ("li8", ""), 0x36: ("li16", ""), 0x37: ("li32", ""), 0x38: ("lf32", ""), 0x39: ("lf64", ""),
    0x3A: ("si8", ""), 0x3B: ("si16", ""), 0x3C: ("si32", ""), 0x3D: ("sf32", ""), 0x3E: ("sf64", ""),
    0x50: ("sxi1", ""), 0x51: ("sxi8", ""), 0x52: ("sxi16", ""),
}


def disasm(abc, code):
    r = R(code); out = []
    while r.p < len(code):
        at = r.p; op = r.u8()
        name, kinds = OPS.get(op, ("op_%02x" % op, ""))
        args = []
        if kinds == "X":
            base = r.s24(); c = r.u30(); offs = [r.s24() for _ in range(c + 1)]
            args = ["default->%d" % (at + base)] + ["%d" % (at + o) for o in offs]
        else:
            for k in kinds:
                if k == "u":
                    args.append(str(r.u30()))
                elif k == "b":
                    v = r.u8(); args.append(str(v - 256 if v > 127 and name == "pushbyte" else v))
                elif k == "o":
                    o = r.s24(); args.append("->%d" % (r.p + o))
                elif k == "m":
                    args.append(abc.mname(r.u30()))
                elif k == "s":
                    args.append(repr(abc.strings[r.u30()]))
                elif k == "i":
                    args.append(str(abc.ints[r.u30()]))
                elif k == "d":
                    args.append(str(abc.doubles[r.u30()]))
        if name == "pushshort":
            v = int(args[0]); args = [str(v - (1 << 30) if v & (1 << 29) else v)]
        out.append("%6d  %s %s" % (at, name, " ".join(args)))
    return out


def load(path):
    cache = path + ".abc.pickle"
    import __main__
    __main__.ABC = ABC
    if os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(path):
        return pickle.load(open(cache, "rb"))
    abcs = []
    for code, data in swf_tags(path):
        if code == 82:
            r = R(data); r.p = 4
            while data[r.p] != 0:
                r.p += 1
            abcs.append(ABC(data[r.p + 1:]))
        elif code == 72:
            abcs.append(ABC(data))
    index = {}
    for ai, abc in enumerate(abcs):
        for (name, iinit, traits), (cinit, ctraits) in zip(abc.instances, abc.classes):
            cname = abc.mname(name)
            index[cname + ".<init>"] = (ai, iinit)
            index[cname + ".<cinit>"] = (ai, cinit)
            for tn, kind, mi in traits + ctraits:
                if mi is not None:
                    key = cname + "." + abc.short(tn) + ("" if kind == "m" else "/" + kind)
                    index[key] = (ai, mi)
    pickle.dump((abcs, index), open(cache, "wb"))
    return abcs, index


if __name__ == "__main__":
    path, cmd = sys.argv[1], sys.argv[2]
    abcs, index = load(path)
    if cmd == "find":
        pat = re.compile(sys.argv[3], re.I)
        for k in sorted(index):
            if pat.search(k):
                print(k)
    elif cmd == "dis":
        pat = re.compile(sys.argv[3])
        for k in sorted(index):
            if pat.search(k):
                ai, mi = index[k]
                code = abcs[ai].bodies.get(mi)
                print("==== %s  (method %d, %s bytes)" % (k, mi, len(code) if code else None))
                if code:
                    print("\n".join(disasm(abcs[ai], code)))
    elif cmd == "strings":
        pat = re.compile(sys.argv[3])
        for k in sorted(index):
            ai, mi = index[k]
            code = abcs[ai].bodies.get(mi)
            if code and any(pat.search(line) for line in disasm(abcs[ai], code)):
                print(k)
