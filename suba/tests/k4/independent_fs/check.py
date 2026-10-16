#!/usr/bin/env python3
"""Independent K2/K3 regressions on a frozen K4 protected filesystem kernel.

Only fixture namespace spelling is adapted: /boot/1 is the explicit RAM image
provider, /work is the real cwd. No production source is changed. Kernel reuse
checks every actual compiled kernel input, compiler identity and ELF digest.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from kernel_probe import build
from check_k2 import sha
from mkfs import format_disk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--kernel-from', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', choices=['memory', 'streams', 'spawn_invalid', 'tree',
                        'orphan_tree', 'blocked_writer', 'protection', 'file_capacity'], required=True)
    args = parser.parse_args()
    source, out, compiler = args.kernel_from.resolve(), args.out.resolve(), args.compiler.resolve()
    previous = json.loads((source / 'verification.json').read_text())
    assert previous['passed'] and previous['case'] == 'filesystem'
    assert previous['compiler_sha256'] == sha(compiler)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'build').mkdir()
    for name, expected in previous['compiled_inputs'].items():
        assert sha(source / name) == expected, name
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    for name in ['tests/k0/boot.vt', 'tests/k0/fw_cfg.vt']:
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    record = dict(case=args.case, compiler_sha256=sha(compiler),
                  source_report_sha256=sha(source / 'verification.json'),
                  passed=False, fixture_adaptations={})
    common = ['abi/contract.vt', 'abi/syscalls.vt', 'abi/argument_wire.vt',
              'user/libsuba/syscall.vt', 'user/libsuba/services.vt',
              'user/libsuba/arguments.vt', 'user/libsuba/argument_builder.vt']
    if args.case == 'file_capacity':
        fixtures = ['tests/k4/independent_fs/file_capacity.vt', 'tests/k4/independent_fs/file_capacity_worker.vt']
        extras = ['abi/files.vt', 'user/libsuba/files.vt']
    elif args.case == 'protection':
        fixtures = ['tests/k4/independent_fs/protection.vt', 'tests/k4/independent_fs/protection_worker.vt']
        extras = []
    else:
        fixtures = [f'tests/k3/{args.case}.vt', 'tests/k3/worker.vt']
        extras = ['tests/k3/common.vt']
        for name in fixtures + extras:
            original = (ROOT / name).read_text()
            adapted = original.replace('services::spawn("1",', 'services::spawn("/boot/1",')
            adapted = adapted.replace('"/boot"', '"/work"')
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(adapted)
            record['fixture_adaptations'][name] = dict(original_sha256=sha(ROOT / name),
                                                        adapted_sha256=sha(target))
    programs = [dict(entry='test::program::run', sources=common + extras + [fixture],
                     assembly=['user/libsuba/syscall.s0']) for fixture in fixtures]
    if args.case == 'protection':
        programs[1]['assembly'] += ['tests/k4/independent_fs/protection.s0']
    try:
        run = build(compiler, out, programs, record, source)
        tree = out / 'initial'
        for directory in ('sys', 'work', 'jobs'):
            (tree / directory).mkdir(parents=True)
        if args.case == 'file_capacity':
            (tree / 'work/shared').write_bytes(b'stable')
        record['initial_disk'] = format_disk(tree, out / 'disk.raw', source / 'abi/contract.vt')
        run += ['-global', 'virtio-mmio.force-legacy=false', '-drive',
                f'file={out}/disk.raw,if=none,format=raw,id=blk,cache=writeback',
                '-device', 'virtio-blk-device,drive=blk']
        record['run_command'] = run
        result = subprocess.run(run, capture_output=True, timeout=180)
        log = result.stdout + result.stderr
        (out / 'boot.log').write_bytes(log)
        record['exit'] = result.returncode
        record['log_sha256'] = sha(out / 'boot.log')
        assert result.returncode == 0, log[-1600:]
        assert b'suba K4: mounted boot=1\n' in log, log[-1600:]
        assert b'suba K3: root exit 0\n' in log, log[-1600:]
        assert b'suba K4: resource baseline\n' in log, log[-1600:]
        assert b'panic' not in log and b'!0000' not in log, log[-1600:]
        if args.case == 'protection':
            assert log.count(b'suba K3: user fault isolated\n') == 6, log[-1600:]
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Independent K4 regression passed:', args.case, flush=True)


if __name__ == '__main__':
    main()
