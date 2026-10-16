#!/usr/bin/env python3
"""Compile the ABI byte probe and compare with an independent fixed-format oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT.parent / 'biomiya'


def oracle():
    data = bytearray(16384)
    def put(offset, value, width=4):
        data[offset:offset+width] = value.to_bytes(width, 'little')
    put(0, 0x314f464e49425553, 8)
    for offset, value in [(8, 1), (12, 512), (64, 1), (68, 0x12345678), (72, 1)]:
        put(offset, value)
    for offset, value in [(16, 0x80000000), (24, 0x20000000), (32, 0x80300000),
                          (40, 0x1000), (48, 0x80400000), (56, 0x80440000),
                          (128, 0x80200000), (136, 0x200000)]:
        put(offset, value, 8)
    for reg in range(1, 32):
        put(512+(reg-1)*8, reg*0x101, 8)
    for offset, value in [(248, 0x10000), (256, 32), (264, 8), (272, 0xdeadbeef)]:
        put(512+offset, value, 8)
    put(1024, 0x3156475241425553, 8)
    for offset, value in [(8, 1), (12, 4096), (16, 1), (40, 576), (44, 1), (48, 2),
                          (64, 577), (68, 1)]:
        put(1024+offset, value)
    put(1048, 257, 8)
    put(1056, 258, 8)
    put(1600, 0x612f, 2)
    for offset, value in [(0, 1), (4, 64), (8, 2), (32, 100), (36, 200), (40, 1)]:
        put(5120+offset, value)
    put(5136, 257, 8)
    put(5144, 3, 8)
    put(6144, 0x31544f4f42425553, 8)
    for offset, value in [(8, 1), (12, 4096), (16, 1), (48, 1), (52, 4096), (56, 0x12345678)]:
        put(6144+offset, value)
    for offset, value in [(0, 1), (16, 1), (20, 1), (32, 193), (36, 193)]:
        put(10240+offset, value)
    put(10248, 7, 8)
    put(10264, 5, 8)
    put(10280, 97, 1)
    put(11264, 0x31534641425553, 8)
    for offset, value in [(8, 1), (12, 4096), (16, 48896), (20, 1), (24, 64),
                          (28, 65), (32, 4096), (36, 193), (40, 1)]:
        put(11264+offset, value)
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    inputs = {'contract.vt': ROOT/'abi/contract.vt', 'probe.vt': ROOT/'tests/k0/abi.vt',
              'linux.vt': CORE/'compiler/runtime/linux.vt', 'linux.s0': CORE/'compiler/runtime/linux.s0'}
    for name, source in inputs.items():
        shutil.copyfile(source, out/name)
    (out/'program.build').write_text('format 1\nprofile linux-user\nentry test::abi::run\n'
                                    'source contract.vt\nsource probe.vt\nsource linux.vt\n'
                                    'assembly linux.s0\noutput probe.elf\n')
    expected = oracle()
    (out/'expected.bin').write_bytes(expected)
    record = {'compiler_sha256': hashlib.sha256(compiler.read_bytes()).hexdigest(),
              'inputs': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.values()},
              'commands': [], 'passed': False,
              'scope': 'ABI constants, seven serialized record byte layouts, six geometry checks; not an OS decoder'}
    def run(command, expected_code):
        result = subprocess.run(command, cwd=out, capture_output=True, timeout=120)
        record['commands'].append({'command': command, 'returncode': result.returncode,
                                   'stdout': result.stdout.decode(errors='replace'),
                                   'stderr': result.stderr.decode(errors='replace')})
        if result.returncode != expected_code:
            raise RuntimeError(f'expected exit {expected_code}, got {result.returncode}')
    try:
        run(['qemu-riscv64', '-s', '1048576', str(compiler), 'build', 'program.build'], 0)
        run(['qemu-riscv64', '-s', '1048576', str(out/'probe.elf')], 0)
        if (out/'actual.bin').read_bytes() != expected:
            raise RuntimeError('serialized output differs from fixed oracle')
        (out/'actual.bin').unlink()
        wrong = bytearray(expected)
        wrong[760] ^= 1  # Independent wrong sepc byte must be rejected before save.
        (out/'expected.bin').write_bytes(wrong)
        run(['qemu-riscv64', '-s', '1048576', str(out/'probe.elf')], 12)
        if (out/'actual.bin').exists():
            raise RuntimeError('negative control published output')
        record['passed'] = True
    finally:
        (out/'verification.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'passed': True, 'commands': len(record['commands']), 'record': str(out/'verification.json')}))


if __name__ == '__main__':
    main()
