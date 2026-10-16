#!/usr/bin/env python3
"""Record source size, ELF segments and conservative frame sum for the frozen backend."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    args = parser.parse_args()
    sources = []
    for line in (ROOT/'kernel/kernel.build').read_text().splitlines():
        if line.startswith(('source ', 'assembly ')):
            sources.append(line.split(' ', 1)[1])
    costs = {name: dict(lines=len((ROOT/name).read_bytes().splitlines()),
                       bytes=(ROOT/name).stat().st_size) for name in sources}
    raw = args.elf.read_bytes()
    phoff = struct.unpack_from('<Q', raw, 32)[0]
    width, count = struct.unpack_from('<HH', raw, 54)
    segments = []
    frames = []
    for i in range(count):
        kind, flags, offset, va, pa, filesz, memsz, align = struct.unpack_from(
            '<IIQQQQQQ', raw, phoff+i*width)
        if kind != 1: continue
        segments.append(dict(flags=flags, address=va, file_bytes=filesz, memory_bytes=memsz))
        if flags != 5: continue
        words = struct.unpack('<'+'I'*(filesz//4), raw[offset:offset+filesz])
        for index, word in enumerate(words):
            if word != 0x00010f13: continue
            cursor, value = index+1, 0
            while cursor < len(words) and words[cursor] != 0x41f10133:
                ins = words[cursor]
                opcode, rd, fn, rs = ins&127, (ins>>7)&31, (ins>>12)&7, (ins>>15)&31
                immediate = ins>>20
                if opcode != 19 or rd != 31: raise RuntimeError('unknown frame prologue')
                if fn == 0 and rs in (0,31):
                    if immediate&0x800: immediate -= 4096
                    value = (0 if rs == 0 else value)+immediate
                elif fn == 1 and rs == 31 and immediate == 12:
                    value <<= 12
                else: raise RuntimeError('unknown frame constant')
                cursor += 1
            if cursor == len(words) or value <= 0 or value%16:
                raise RuntimeError('unknown frame size')
            frames.append(dict(address=va+index*4, bytes=value))
    function_count = sum(len(re.findall(r'(?m)^(?:pub )?(?:unsafe )?fn ', (ROOT/name).read_text()))
                         for name in sources if name.endswith('.vt'))
    if len(frames) != function_count: raise RuntimeError('function/prologue count mismatch')
    print(json.dumps(dict(elf=str(args.elf.resolve()), sha256=hashlib.sha256(raw).hexdigest(),
        source=costs, source_lines=sum(c['lines'] for c in costs.values()),
        source_bytes=sum(c['bytes'] for c in costs.values()), segments=segments,
        frames=frames, max_frame=max(f['bytes'] for f in frames),
        all_frames_sum=sum(f['bytes'] for f in frames),
        bound_premise='No recursive/indirect calls, serialized early boot. Sum counts every VT frame once; '
                      'S0 leaf/stub stack allowance must be audited separately.'), indent=2))

if __name__ == '__main__':
    main()
