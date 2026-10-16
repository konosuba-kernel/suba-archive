#!/usr/bin/env python3
"""Actual protected-kernel storage fixtures; host only builds initial input images."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import re
from kernel_probe import ROOT, snapshot, build
from check_k2 import sha
from mkfs import format_disk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', choices=['filesystem', 'boundaries', 'disk_full', 'node_full', 'cwd', 'cancel_pre', 'cancel_dma', 'cancel_no_irq', 'cancel_reserve', 'disk_partial', 'unlink_reader', 'transient_owner', 'cwd_identity'], default='filesystem')
    parser.add_argument('--kernel-from', type=Path)
    args = parser.parse_args()
    compiler, out = args.compiler.resolve(), args.out.resolve()
    record = dict(case=args.case, inputs=snapshot(out), compiler_sha256=sha(compiler), passed=False)
    try:
        entry = out / 'kernel/entry.vt'
        code = entry.read_text().replace('static mut INFO:', 'static mut TEST_BASELINE: usize = 0;\nstatic mut INFO:')
        code = code.replace('        dispatch::sources(IMAGES);',
                            '        TEST_BASELINE = memory::stats().free;\n        dispatch::sources(IMAGES);')
        anchor = '                process::Selection::Idle => {'
        assert code.count(anchor) == 1
        code = code.replace(anchor, anchor + '''
                    if dispatch::quiescent() {
                        match fs::shutdown_step() {
                            fs::Progress::Invalid => { let stopped: u32 = panic(74); return 0; },
                            fs::Progress::More => { continue; }, fs::Progress::Wait => { continue; },
                            fs::Progress::Ready => {}
                        }
                        if memory::stats().free != TEST_BASELINE { let stopped: u32 = panic(90); return 0; }
                        machine::text("suba K4: resource baseline\\n");
                        machine::text("suba K4: user IRQ traps "); dispatch::number(hub::user_traps()); machine::text("\\n");
                        let failed: bool = machine::power_off();
                        let stopped: u32 = panic(72); return 0;
                    }''')
        entry.write_text(code)
        if args.case.startswith('cancel_'):
            sys.path.insert(0, str(ROOT / 'tests/k4'))
            from controls import install_cancel
            install_cancel(out, args.case)
        common = ['abi/contract.vt', 'abi/syscalls.vt', 'abi/argument_wire.vt',
                  'user/libsuba/syscall.vt', 'user/libsuba/services.vt', 'user/libsuba/arguments.vt',
                  'user/libsuba/argument_builder.vt', 'abi/files.vt', 'user/libsuba/files.vt']
        fixtures = ['tests/k4/' + args.case + '.vt']
        if args.case == 'cwd':
            fixtures.append('tests/k4/cwd_worker.vt')
        if args.case == 'transient_owner':
            fixtures.append('tests/k4/transient_attacker.vt')
        if args.case == 'cwd_identity':
            fixtures += ['tests/k4/cwd_identity_child.vt', 'tests/k4/cwd_identity_grandchild.vt']
        if args.case.startswith('cancel_'):
            fixtures = ['tests/k4/cancellation.vt', 'tests/k4/cancel_worker.vt']
        programs = [dict(entry='test::program::run', sources=common + [fixture],
                         assembly=['user/libsuba/syscall.s0']) for fixture in fixtures]
        run = build(compiler, out, programs, record, args.kernel_from.resolve() if args.kernel_from else None)
        tree = out / 'initial'
        for directory in ['sys', 'work', 'jobs']:
            (tree / directory).mkdir(parents=True)
        if args.case in ('disk_full', 'node_full', 'cwd', 'cancel_pre', 'cancel_dma', 'cancel_no_irq', 'cancel_reserve', 'disk_partial'):
            (tree / 'work/probe').write_bytes(b'old')
        else:
            (tree / 'work/中文.vt').write_text('module hello; // 中文\n')
        if args.case in ('disk_full', 'disk_partial', 'cancel_reserve'):
            hole_blocks = 0 if args.case == 'disk_full' else 8
            if hole_blocks:
                (tree / 'work/aaa_hole').write_bytes(bytes(hole_blocks * 4096))
            remaining = (48896 - 193 - 1 - hole_blocks) * 4096
            index = 0
            while remaining:
                size = min(remaining, 16 * 1024 * 1024)
                with (tree / f'work/full{index:02d}').open('wb') as stream:
                    stream.truncate(size)
                remaining -= size
                index += 1
        if args.case == 'node_full':
            for index in range(4091):
                (tree / f'work/n{index:04d}').touch()
        record['initial_disk'] = format_disk(tree, out / 'disk.raw', ROOT / 'abi/contract.vt')
        run += ['-global', 'virtio-mmio.force-legacy=false', '-drive',
                f'file={out}/disk.raw,if=none,format=raw,id=blk,cache=writeback',
                '-device', 'virtio-blk-device,drive=blk']
        record['run_command'] = run
        record['boots'] = []
        for index in range(2):
            if args.case == 'cancel_no_irq':
                try:
                    result = subprocess.run(run, capture_output=True, timeout=8)
                    log = result.stdout + result.stderr
                except subprocess.TimeoutExpired as stopped:
                    log = (stopped.stdout or b'') + (stopped.stderr or b'')
                (out / f'boot{index}.log').write_bytes(log)
                assert b'suba kernel panic reason=73\n' in log, log[-1500:]
                assert b'suba K4: observed user cancel window\n' in log, log[-1500:]
                assert b'suba K4: resource baseline\n' not in log, log[-1500:]
                record['boots'].append(dict(expected='pending DMA rejected without U IRQ', log_sha256=sha(out / f'boot{index}.log')))
                break
            try:
                result = subprocess.run(run, capture_output=True, timeout=180)
            except subprocess.TimeoutExpired as stopped:
                log = (stopped.stdout or b'') + (stopped.stderr or b'')
                (out / f'boot{index}.log').write_bytes(log)
                record['timeout_boot'] = index
                raise
            log = result.stdout + result.stderr
            (out / f'boot{index}.log').write_bytes(log)
            assert result.returncode == 0, log[-1000:]
            assert f'suba K4: mounted boot={index + 1}\n'.encode() in log, log[-1000:]
            assert b'suba K3: root exit 0\n' in log and b'suba K4: resource baseline\n' in log, log[-1000:]
            assert b'panic' not in log and b'!0000' not in log, log[-1000:]
            if args.case.startswith('cancel_'):
                assert log.count(b'suba K4: observed user cancel window\n') == 100, log[-1500:]
            if args.case == 'cancel_dma':
                traps = re.search(rb'suba K4: user IRQ traps (\d+)', log)
                assert traps and int(traps.group(1)) >= 100, log[-1500:]
            record['boots'].append(dict(exit=result.returncode, log_sha256=sha(out / f'boot{index}.log')))
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print(f'K4 {args.case}: expected outcomes verified')


if __name__ == '__main__':
    main()
