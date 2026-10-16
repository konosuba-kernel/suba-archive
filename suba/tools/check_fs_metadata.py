#!/usr/bin/env python3
"""Compile production FS codecs/validator and compare with independent v1 bytes.

Linux syscalls only transport test bytes; this is not a device/persistence test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def superblock(serial=0):
    data = bytearray(4096)
    struct.pack_into('<Q10I', data, 0, 0x31534641425553, 1, 4096, 48896,
                     1, 64, 65, 4096, 193, 0, 0)
    struct.pack_into('<Q', data, 48, serial)
    checksum(data)
    return data


def checksum(data):
    struct.pack_into('<I', data, 44, 0)
    struct.pack_into('<I', data, 44, zlib.crc32(data[:4096]))


def node(kind=1, flags=0, generation=1, parent=0, name=b'f', size=0, first=0, last=0):
    data = bytearray(128)
    if isinstance(name, str):
        name = name.encode('utf-8')
    struct.pack_into('<IIQIIQII', data, 0, kind, flags, generation, parent, len(name), size, first, last)
    data[40:40 + len(name)] = name
    return data


def put_node(data, index, value):
    data[266240 + index * 128:266240 + (index + 1) * 128] = value


def put_fat(data, index, value):
    struct.pack_into('<I', data, 4096 + index * 4, value)


def metadata():
    data = bytearray(790528)
    data[:4096] = superblock()
    for index in list(range(193)) + list(range(48896, 65536)):
        put_fat(data, index, 0xfffffffe)
    put_node(data, 0, node(kind=2, name=b''))
    return data


def codec_cases(run):
    header = superblock()
    run('encode-super', b'\0', expected=header)
    run('decode-super', b'\1' + header)
    for serial in (1, 0x100000000, 0xffffffffffffffff):
        run('decode-boot-serial-' + str(serial), b'\1' + superblock(serial))
    for offset in (0, 7, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 56, 4095):
        data = bytearray(header)
        data[offset] ^= 1
        run('corrupt-super-' + str(offset), b'\1' + data, code=1)
        if offset not in (44, 48):
            checksum(data)
            run('invalid-super-layout-' + str(offset), b'\1' + data, code=1)
    run('short-super', b'\1' + header[:-1], code=1)
    rng = random.Random(4104)
    for index, size in enumerate([0, 1, 4, 9, 128, 4096] + [rng.randrange(4097) for _ in range(30)]):
        data = rng.randbytes(size)
        run('crc-' + str(index), b'\2' + data, expected=struct.pack('<I', zlib.crc32(data)))
    for name, data, op in (
        ('file', node(), 3), ('max-file', node(size=16777216, first=193, last=4288), 3),
        ('root', node(kind=2, name=b''), 4), ('directory', node(kind=2), 3),
        ('free-generation', node(kind=0, generation=33, name=b''), 3),
        ('emoji', node(name='😀'), 3), ('max-name', node(name='a' * 63), 3),
        ('transient', node(flags=1), 3), ('detached', node(flags=2), 3),
    ):
        run(name, bytes([op]) + data, expected=data)
    invalid = {
        'free-data': node(kind=0), 'kind': node(kind=3), 'zero-generation': node(generation=0),
        'parent': node(parent=4096), 'too-large': node(size=16777217, first=193, last=194),
        'metadata-first': node(size=1, first=192, last=193),
        'outside-last': node(size=1, first=193, last=48896),
        'empty-chain': node(first=193), 'missing-chain': node(size=1),
        'directory-size': node(kind=2, size=1), 'directory-flags': node(kind=2, flags=1),
        'unknown-flags': node(flags=4), 'empty-name': node(name=b''),
        'dot': node(name=b'.'), 'parent-name': node(name=b'..'), 'slash': node(name=b'a/b'),
        'nul': node(name=b'a\0b'), 'overlong-utf8': node(name=b'\xc0\x80'),
        'surrogate': node(name=b'\xed\xa0\x80'), 'long-name': node(name='a' * 64),
    }
    for name, data in invalid.items():
        run('invalid-' + name, b'\3' + data, code=1)
    for offset in (41, 103, 104, 127):
        data = node()
        data[offset] = 1
        run('node-reserved-' + str(offset), b'\3' + data, code=1)
    for name, data in (('file', node(name=b'')), ('free', node(kind=0, name=b'')),
                       ('parent', node(kind=2, name=b'', parent=1)), ('name', node(kind=2))):
        run('invalid-root-' + name, b'\4' + data, code=1)


def mount_cases(run):
    def reject(name, data, kind, index):
        run(name, data, code=3, expected=struct.pack('<II', kind, index))

    run('empty', metadata(), expected=None)
    data = metadata()
    put_node(data, 1, node(kind=2, name='源码'))
    put_node(data, 2, node(parent=1, name=b'hello.vt', size=4097, first=193, last=194))
    put_fat(data, 193, 194)
    put_fat(data, 194, 0xffffffff)
    run('nested-chain', data, expected=None)
    # Legal synced lifecycle states still own every block until boot-time cleanup.
    for flags in (1, 2, 3):
        data = metadata()
        put_node(data, 1, node(flags=flags, size=4096, first=193, last=193))
        put_fat(data, 193, 0xffffffff)
        run('lifecycle-flags-' + str(flags), data, expected=None)
        put_node(data, 2, node(name=b'other', size=4096, first=193, last=193))
        reject('lifecycle-shared-block-' + str(flags), data, 9, 193)
        put_node(data, 2, node(kind=0, generation=0, name=b''))
        put_fat(data, 193, 0)
        reject('lifecycle-broken-chain-' + str(flags), data, 10, 1)
    data = metadata()
    put_node(data, 1, node(flags=2))
    put_node(data, 2, node())
    run('detached-name-is-not-visible', data, expected=None)
    put_node(data, 1, node(flags=1))
    reject('transient-name-still-visible', data, 7, 2)
    put_node(data, 1, node(flags=2, parent=3))
    reject('detached-invalid-parent', data, 5, 1)
    data = metadata()
    put_node(data, 1, node(flags=3, size=65 * 4096, first=193, last=257))
    for index in range(193, 257):
        put_fat(data, index, index + 1)
    put_fat(data, 257, 0xffffffff)
    run('lifecycle-over-one-reaper-slice', data, expected=None)
    for name, index, value, fault in (
        ('metadata-fat', 100, 0, 2), ('outside-fat', 50000, 0, 2),
        ('data-reserved', 194, 0xfffffffe, 3), ('invalid-next', 194, 1, 3),
        ('orphan-block', 194, 0xffffffff, 11),
    ):
        data = metadata()
        put_fat(data, index, value)
        reject(name, data, fault, index)
    data = metadata()
    put_node(data, 1, node(parent=2))
    reject('free-parent', data, 5, 1)
    data = metadata()
    put_node(data, 1, node(kind=2, parent=2, name=b'a'))
    put_node(data, 2, node(kind=2, parent=1, name=b'b'))
    reject('parent-cycle', data, 6, 1)
    data = metadata()
    for index in range(1, 17):
        put_node(data, index, node(kind=2, parent=index - 1, name=b'a'))
    run('depth16', data, expected=None)
    put_node(data, 17, node(kind=2, parent=16, name=b'a'))
    reject('depth17', data, 6, 17)
    data = metadata()
    put_node(data, 1, node())
    put_node(data, 2, node())
    reject('duplicate-name', data, 7, 2)
    for name, size, last, next_block, fault, index in (
        ('short-chain', 8192, 194, 0xffffffff, 8, 1),
        ('long-chain', 4096, 193, 194, 10, 1),
        ('chain-cycle', 8192, 194, 193, 9, 193),
        ('wrong-last', 4096, 194, 0xffffffff, 10, 1),
        ('free-chain', 4096, 193, 0, 10, 1),
    ):
        data = metadata()
        put_node(data, 1, node(size=size, first=193, last=last))
        put_fat(data, 193, next_block)
        put_fat(data, 194, 0xffffffff)
        reject(name, data, fault, index)
    data = metadata()
    for index, name in ((1, b'a'), (2, b'b')):
        put_node(data, index, node(name=name, size=4096, first=193, last=193))
    put_fat(data, 193, 0xffffffff)
    reject('shared-block', data, 9, 193)
    data = metadata()
    put_node(data, 1, node(size=16777216, first=193, last=4288))
    for index in range(193, 4288):
        put_fat(data, index, index + 1)
    put_fat(data, 4288, 0xffffffff)
    run('max-file', data, expected=None)
    data = metadata()
    for index in range(1, 4096):
        put_node(data, index, node(name=f'f{index:04}'.encode()))
    run('4096-nodes', data, expected=None)
    put_node(data, 4095, node(name=b'f0001'))
    reject('last-duplicate', data, 7, 4095)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    compiler, out = args.compiler.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = ['abi/contract.vt', 'user/text/utf8.vt', 'kernel/fs/codec.vt',
               'kernel/fs/mount_check.vt', 'tests/k6/transport.vt', 'tools/fontpack/linux.s0',
               'tests/k4/metadata/codec_probe.vt', 'tests/k4/metadata/mount_probe.vt']
    record = dict(passed=False, compiler_sha256=digest(compiler),
                  scope='native pure codec/allocation validator; no guest device claim',
                  inputs={}, cases=[])
    try:
        for name in sources:
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
            record['inputs'][name] = digest(target)
        record['inputs']['tools/check_fs_metadata.py'] = digest(Path(__file__))
        for mode, cases in (('codec', codec_cases), ('mount', mount_cases)):
            names = sources[:5] + [f'tests/k4/metadata/{mode}_probe.vt']
            manifest = f'format 1\nprofile linux-user\nentry test::{mode}_probe::run\n'
            manifest += ''.join('source ' + name + '\n' for name in names)
            manifest += f'assembly tools/fontpack/linux.s0\noutput {mode}.elf\n'
            (out / (mode + '.build')).write_text(manifest)
            command = ['qemu-riscv64', '-s', '1048576', str(compiler), 'build', mode + '.build']
            built = subprocess.run(command, cwd=out, capture_output=True, timeout=180)
            (out / (mode + '-build.log')).write_bytes(built.stdout + built.stderr)
            assert built.returncode == 0, built.stdout + built.stderr
            record[mode + '_elf_sha256'] = digest(out / (mode + '.elf'))

            def run(name, data, code=0, expected=b''):
                start = time.monotonic()
                result = subprocess.run(['qemu-riscv64', '-s', '1048576', str(out / (mode + '.elf'))],
                                        input=data, capture_output=True, timeout=30)
                valid_output = result.stdout == expected
                if expected is None:
                    valid_output = len(result.stdout) == 4 and 0 < struct.unpack('<I', result.stdout)[0] <= 200000
                ok = result.returncode == code and valid_output and not result.stderr
                record['cases'].append(dict(name=mode + '/' + name, passed=ok, exit=result.returncode,
                    result=result.stdout.hex(), seconds=time.monotonic() - start,
                    input_sha256=hashlib.sha256(data).hexdigest()))
                assert ok, (record['cases'][-1], result.stderr)
            cases(run)
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print(f"FS metadata: {len(record['cases'])} native codec/allocation cases passed")


if __name__ == '__main__':
    main()
