#!/usr/bin/env python3
"""Reject stale identities, corrupt ELF, profile overflow and oversized transport."""
import argparse
import json
from pathlib import Path
import struct
from unittest.mock import patch
import ram_launch
from check_k2 import sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--desktop', type=Path, required=True)
    parser.add_argument('--disk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    original = args.kernel.read_bytes()
    changed = bytearray(original)
    changed[4096] ^= 1
    bad_header = bytearray(original)
    bad_header[0] = 0
    bad_range = bytearray(original)
    table = struct.unpack_from('<Q', bad_range, 32)[0]
    struct.pack_into('<QQ', bad_range, table + 16, 0x84400000, 0x84400000)
    cases = [('stale-identity', original, '0' * 64),
             ('changed-content', bytes(changed), sha(args.kernel)),
             ('bad-header', bytes(bad_header), None),
             ('outside-kernel-window', bytes(bad_range), None),
             ('over-file-limit', original + bytes(0x1000001 - len(original)), None)]
    result = {'passed': False, 'cases': []}
    for name, data, expected in cases:
        kernel = out / (name + '.elf')
        kernel.write_bytes(data)
        destination = out / name
        try:
            ram_launch.prepare(args.boot.resolve(), kernel, args.desktop.resolve(), args.disk.resolve(),
                               destination, expected or sha(kernel))
        except (AssertionError, ValueError, struct.error) as error:
            assert not destination.exists(), 'rejected input created deployment'
            result['cases'].append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise AssertionError('bad input accepted: ' + name)
    # Successful copying is not enough: detect changes between preparation and launch.
    prepared = out / 'prepared'
    ram_launch.prepare(args.boot.resolve(), args.kernel.resolve(), args.desktop.resolve(),
                       args.disk.resolve(), prepared, sha(args.kernel))
    ram_launch.validate(prepared)
    for name in ('kernel.elf', 'boot.elf', 'desktop.elf', 'start.bin'):
        path = prepared / name
        saved = path.read_bytes()
        changed = bytearray(saved)
        changed[-1] ^= 1
        path.write_bytes(changed)
        try:
            ram_launch.validate(prepared)
        except ValueError as error:
            result['cases'].append({'name': 'after-copy-' + name, 'rejected': True, 'reason': str(error)})
        else:
            raise AssertionError('changed launch artifact accepted: ' + name)
        finally:
            path.write_bytes(saved)
    ram_launch.validate(prepared)
    # A deterministic change after validation but before copy must fail closed.
    racing = out / 'racing.elf'
    racing.write_bytes(original)
    copy = ram_launch.shutil.copyfile
    def change_then_copy(source, target):
        if source == racing:
            altered = bytearray(original)
            altered[4096] ^= 1
            racing.write_bytes(altered)
        return copy(source, target)
    destination = out / 'racing-deployment'
    with patch.object(ram_launch.shutil, 'copyfile', change_then_copy):
        try:
            ram_launch.prepare(args.boot.resolve(), racing, args.desktop.resolve(), args.disk.resolve(),
                               destination, sha(args.kernel))
        except ValueError as error:
            assert not (destination / 'deployment.json').exists()
            result['cases'].append({'name': 'source-change-during-copy', 'rejected': True, 'reason': str(error)})
        else:
            raise AssertionError('source race accepted')
    result['passed'] = True
    (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('RAM transport: invalid inputs, post-copy changes and source-copy race rejected')


if __name__ == '__main__':
    main()
