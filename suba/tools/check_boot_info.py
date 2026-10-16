#!/usr/bin/env python3
"""Exercise the production BootInfo decoder without following described addresses."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    compiler, out = args.compiler.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    files = {'contract.vt': ROOT/'abi/contract.vt', 'boot_info.vt': ROOT/'platform/boot_info.vt',
             'probe.vt': ROOT/'tests/k2_ram/boot_info_probe.vt',
             'linux.vt': ROOT.parent/'biomiya/compiler/runtime/linux.vt',
             'linux.s0': ROOT.parent/'biomiya/compiler/runtime/linux.s0'}
    for name, path in files.items():
        shutil.copyfile(path, out/name)
    (out/'probe.build').write_text('format 1\nprofile linux-user\nentry test::boot_info::run\n'
        'source contract.vt\nsource boot_info.vt\nsource linux.vt\nsource probe.vt\n'
        'assembly linux.s0\noutput probe.elf\n')
    report = dict(passed=False, compiler_sha256=digest(compiler), tool_sha256=digest(Path(__file__)),
                  inputs={str(p): digest(p) for p in files.values()}, cases=[])
    def case(name, data, expected=1):
        command = ['qemu-riscv64', str(out/'probe.elf')]
        result = subprocess.run(command, input=data, capture_output=True, timeout=10)
        item = dict(name=name, input_hex=data.hex(), expected=expected, exit=result.returncode,
                    command=command, stderr=result.stderr.decode(errors='replace'))
        report['cases'].append(item)
        if result.returncode != expected:
            raise RuntimeError(f'{name}: expected {expected}, got {result.returncode}')
    base = bytearray(512)
    def put(data, at, value, width=8):
        data[at:at+width] = value.to_bytes(width, 'little')
    for at,value,width in [(0,0x314f464e49425553,8),(8,1,4),(12,512,4),
            (16,0x80000000,8),(24,0x20000000,8),(32,0x80210000,8),(40,40,8),
            (48,0x80400000,8),(56,0x80600000,8),(72,1,4),
            (128,0x80200000,8),(136,0x200000,8)]:
        put(base,at,value,width)
    try:
        command = ['qemu-riscv64','-s','1048576',str(compiler),'build','probe.build']
        result = subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=120)
        report['build'] = dict(command=command,exit=result.returncode,stdout=result.stdout,stderr=result.stderr)
        if result.returncode: raise RuntimeError(str(report['build']))
        report['elf_sha256'] = digest(out/'probe.elf')
        case('valid',base,0)
        for n in range(512): case(f'truncated-{n}',base[:n])
        case('oversize',base+b'\0')
        changes = [(0,0,8),(8,2,4),(12,511,4),(16,0,8),(24,0x10000000,8),
            (32,0x10000000,8),(32,0x803ffff8,8),(32,0x80210001,8),(40,39,8),
            (40,65537,8),(48,0x80401000,8),(56,0x80400000,8),(56,0xffffffffffffffff,8),
            (64,2,4),(72,0,4),(72,17,4),(128,0x7fffffff,8),(128,0xa0000000,8),
            (136,0,8),(136,0xffffffffffffffff,8)]
        for at,value,width in changes:
            data = base.copy()
            put(data, at, value, width)
            case(f'field-{at}-{value}',data)
        for at in [76,127,144,383,384,511]:
            data = base.copy()
            data[at] = 1
            case(f'reserved-byte-{at}', data)
        data = base.copy()
        put(data, 128, 0x80200000)
        put(data, 136, 4096)
        case('dtb-uncovered',data)
        data = base.copy()
        put(data, 72, 16, 4)
        for i in range(1,16):
            put(data, 128+i*16, 0x81000000+i)
            put(data, 136+i*16, 1)
        case('sixteen-overlapping-byte-reservations',data,0)
        data = base.copy()
        put(data, 64, 1, 4)
        put(data, 68, 0xffffffff, 4)
        case('slot-and-opaque-crc',data,0)
        report['passed']=True
    finally:
        (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(report['cases']))))

if __name__=='__main__':
    main()
