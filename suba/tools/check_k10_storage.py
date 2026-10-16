#!/usr/bin/env python3
"""Rerun storage boundary scenarios through the current ordinary FS loader."""
import argparse
import json
import hashlib
import struct
from pathlib import Path
import shutil
import build_users
import kernel_probe
import native_probe
from check_k2 import sha
from mkfs import format_disk, constants
from read_disk import Disk
from check_k10_lifecycle import snapshot
from check_kernel_entry import require

ROOT = Path(__file__).resolve().parents[1]


def inspect_disk(path, contract):
    disk = Disk(path, contract)
    c = disk.c
    allocated = {i for i in range(c['FS_DATA_START'], c['FS_BLOCKS'])
                 if struct.unpack_from('<I', disk.data, c['FS_FAT_START'] * c['BLOCK_BYTES'] + i * 4)[0] != c['FAT_FREE']}
    reached = set()
    files = {}
    for name, index in disk.paths.items():
        node = disk.nodes[index]
        require(node['flags'] == 0, 'temporary/detached state survived sync')
        if node['kind'] != c['NODE_FILE']:
            continue
        data = disk.read(name)
        block = node['first']
        for _ in range((len(data) + c['BLOCK_BYTES'] - 1) // c['BLOCK_BYTES']):
            require(block not in reached, 'shared data block across files')
            reached.add(block)
            block = struct.unpack_from('<I', disk.data, c['FS_FAT_START'] * c['BLOCK_BYTES'] + block * 4)[0]
        files[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), generation=node['generation'])
    require(all(node['flags'] == 0 for node in disk.nodes.values()), 'detached node not in directory paths')
    require(reached == allocated, 'allocated FAT blocks not owned exactly once')
    return dict(nodes=len(disk.nodes), allocated_blocks=len(allocated),
        free_nodes=c['FS_NODE_COUNT'] - len(disk.nodes), free_blocks=c['FS_BLOCKS'] - c['FS_DATA_START'] - len(allocated),
        directories=sorted(name for name, i in disk.paths.items() if disk.nodes[i]['kind'] == c['NODE_DIRECTORY']),
        files=files, disk_sha256=sha(path), boot_serial=struct.unpack_from('<Q', disk.data, c['FS_SUPER_BOOT_SERIAL'])[0])


def check_ledger(case, before, after):
    expected = dict(before['files'])
    directories = before['directories']
    def file(data, generation=1):
        return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), generation=generation)
    if case == 'node_full':
        del expected['/work/n0000']
        expected['/work/replacement'] = file(b'reused', 2)
    elif case == 'disk_partial':
        del expected['/work/aaa_hole']
    elif case == 'boundaries':
        expected['/work/boundary'] = file(b'x' + bytes((i * 17 + 9) % 251 for i in range(65536)))
    elif case == 'unlink_reader':
        expected['/work/unlink/保留'] = file(b'', 2)
        directories = sorted(directories + ['/work/unlink'])
    require(after['files'] == expected, 'published file content/generation differs from expected transition')
    require(after['directories'] == directories, 'unexpected directory transition')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--kernel-from', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', choices=['disk_full', 'node_full', 'disk_partial', 'boundaries', 'unlink_reader', 'unsealed_output'], required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    record = {'passed': False, 'case': args.case, 'compiler_sha256': sha(args.compiler),
              'stage_acceptance': False, 'scope': 'K10 storage preparatory exploration',
              'source_inputs': snapshot(out, args.kernel_from.resolve())}
    dependencies = ['tools/check_k10_storage.py', 'tools/check_k10_lifecycle.py', 'tools/kernel_probe.py',
                    'tools/native_probe.py', 'tools/build_users.py', 'tools/mkfs.py', 'tools/read_disk.py',
                    'tools/check_kernel_entry.py', 'tools/check_k2.py', 'tools/check_k5_devices.py']
    record['tool_inputs'] = {}
    for name in dependencies:
        target = out / 'tool_snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        record['tool_inputs'][name] = sha(target)
    try:
        config = out / 'tests/k10/storage_config.vt'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('module test::storage_config;\npub const FULL_NODES: bool = ' + str(args.case == 'node_full').lower() + ';\npub const FULL_DATA: bool = ' + str(args.case == 'disk_full').lower() + ';\n')
        fixture = 'tests/k10/storage_publish.vt' if args.case == 'unsealed_output' else 'tests/k4/' + args.case + '.vt'
        programs = [dict(entry='test::storage::main', sources=build_users.COMMON + ['tests/k10/storage.vt', 'tests/k10/storage_config.vt'],
                         assembly=['user/libsuba/syscall.s0']),
                    dict(entry='test::program::run', sources=build_users.COMMON + [fixture],
                         assembly=['user/libsuba/syscall.s0'])]
        command = kernel_probe.build(args.compiler.resolve(), out, programs, record, args.kernel_from.resolve())
        tree = out / 'initial'
        for name in ('sys', 'work', 'jobs'):
            (tree / name).mkdir(parents=True)
        shutil.copyfile(out / 'build/user1.elf', tree / 'sys/worker')
        (tree / 'work/probe').write_bytes(b'old')
        c = constants(out / 'abi/contract.vt')
        if args.case in ('disk_full', 'disk_partial'):
            if args.case == 'disk_partial':
                (tree / 'work/aaa_hole').write_bytes(bytes(8 * c['BLOCK_BYTES']))
            allocated = sum((p.stat().st_size + 4095) // 4096 for p in tree.rglob('*') if p.is_file())
            remaining = (c['FS_BLOCKS'] - c['FS_DATA_START'] - allocated) * c['BLOCK_BYTES']
            index = 0
            while remaining:
                count = min(remaining, c['FS_FILE_BYTES_MAX'])
                with (tree / f'work/full{index:02d}').open('wb') as target:
                    target.truncate(count)
                remaining -= count; index += 1
        if args.case == 'node_full':
            count = c['FS_NODE_COUNT'] - 1 - sum(1 for _ in tree.rglob('*'))
            for i in range(count):
                (tree / f'work/n{i:04d}').touch()
        record['initial_disk'] = format_disk(tree, out / 'disk.raw', out / 'abi/contract.vt')
        command = native_probe.devices(command, out / 'disk.raw')
        baseline = inspect_disk(out / 'disk.raw', out / 'abi/contract.vt')
        record['initial_ledger'] = baseline
        record['boots'] = []
        for index in range(2):
            run_out = out / f'boot{index + 1}'
            run_out.mkdir()
            record['boots'].append(native_probe.run(run_out, command, 300))
            ledger = inspect_disk(out / 'disk.raw', out / 'abi/contract.vt')
            check_ledger(args.case, baseline, ledger)
            require(ledger['boot_serial'] == index + 1, 'same-disk boot serial')
            pixels = record['boots'][-1]['stages'][-1]['pixels']
            values = [r * 65536 + g * 256 + b for r, g, b in pixels[1:]]
            require(values[2:] == [ledger['free_blocks'], ledger['free_nodes']], 'guest free counters differ from actual disk allocation')
            record['boots'][-1]['guest_counters'] = dict(zip(['before_blocks', 'before_nodes', 'after_blocks', 'after_nodes'], values))
            record['boots'][-1]['disk_ledger'] = ledger
            (run_out / 'metadata.bin').write_bytes(Disk(out / 'disk.raw', out / 'abi/contract.vt').data[:c['FS_DATA_START'] * c['BLOCK_BYTES']])
        record['passed'] = True
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K10 storage boundary and same-disk reboot passed:', args.case)


if __name__ == '__main__':
    main()
