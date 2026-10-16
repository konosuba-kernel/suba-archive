#!/usr/bin/env python3
"""Protected lifecycle/queue gates on a frozen production kernel.

Two explicit test-only interleavings mark a window owner Dying (i) after the
first CopySurface piece, and (ii) immediately before DesktopKill's state check.
These change scheduling only, use the real terminate/revoke APIs, and never
patch ELF bytes. All other 100 rounds and queue actions use ordinary U syscalls.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
from PIL import Image
import kernel_probe
from check_k2 import sha
from check_kernel_entry import FIRMWARE, require
from check_k5_devices import Qmp

ROOT = Path(__file__).resolve().parents[1]


def observe(out):
    path = out / 'kernel/dispatch_window.vt'
    text = path.read_text().replace('module kernel::dispatch;', '''module kernel::dispatch;
static mut TEST_COPY_KILLED: bool = false;
static mut TEST_EXIT_KILLED: bool = false;''')
    anchor = '        if !window::live(transfer.copy.window) { return finish(work, abi::BAD_HANDLE, 0); }'
    require(text.count(anchor) == 1, 'copy scheduling observer anchor')
    text = text.replace(anchor, '''        if !TEST_COPY_KILLED && !transfer.writing && transfer.done >= 2048_usize {
            TEST_COPY_KILLED = true;
            match window::owner(transfer.copy.window) {
                window::Owner::Invalid => { return false; },
                window::Owner::Ready(target) => {
                    if !process::terminate(target, abi::CANCELLED) { return false; }
                    window::revoke_owner(target);
                    machine::text("K5 COPY REVOKED AFTER FIRST PIECE\\n");
                }
            }
        }
''' + anchor)
    anchor = '                // Exit/fault can mark Dying before Cleanup::Cancel revokes its windows.'
    require(text.count(anchor) == 1, 'dying kill scheduling observer anchor')
    text = text.replace(anchor, '''                if !TEST_EXIT_KILLED {
                    TEST_EXIT_KILLED = true;
                    if !process::terminate(target, 42) { return false; }
                    machine::text("K5 KILL OBSERVES DYING LIVE WINDOW\\n");
                }
''' + anchor)
    path.write_text(text)


def programs(mode):
    common = [line.split(' ', 1)[1] for line in (ROOT / 'user/desktop/desktop.build').read_text().splitlines()
              if line.startswith('source ') and not line.startswith(('source user/desktop/', 'source user/draw/'))]
    common += ['user/libsuba/argument_builder.vt', 'tests/k5/lifecycle.vt']
    names = ['test::k5_lifecycle::copy_race' if mode == 'lifecycle' else 'test::k5_lifecycle::queues',
             'test::k5_lifecycle::producer']
    return [dict(entry=name, sources=common, assembly=['user/libsuba/syscall.s0']) for name in names]


def run(out, command, mode):
    target = out / mode
    target.mkdir()
    command = [part for part in command if part != '-nographic']
    command += ['-serial', 'file:' + str(target / 'serial.log'), '-monitor', 'none',
                '-qmp', 'unix:' + str(target / 'qmp.sock') + ',server=on,wait=off']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    qmp = None
    record = {'passed': False, 'mode': mode, 'command': command, 'rounds': [], 'input_edges': 0}
    start = time.monotonic()
    try:
        while time.monotonic() - start < 30 and not (target / 'qmp.sock').exists():
            require(process.poll() is None, 'QEMU exited before QMP startup')
            time.sleep(.05)
        qmp = Qmp(target / 'qmp.sock')
        sent = False
        while time.monotonic() - start < 240:
            require(process.poll() is None, 'QEMU exited before completion')
            log = (target / 'serial.log').read_text() if (target / 'serial.log').exists() else ''
            require('panic' not in log.lower(), 'kernel panic: ' + log)
            path = target / 'frame.ppm'
            qmp.call('screendump', {'filename': str(path)})
            frame = Image.open(path)
            frame.save(target / 'frame.png')
            pixel = frame.getpixel((0, 0))
            require(pixel[0] != 255, f'protected fixture failed with code {pixel[2]}')
            if pixel == (0, 255, 0):
                if mode == 'lifecycle':
                    require('K5 COPY REVOKED AFTER FIRST PIECE' in log and
                            'K5 KILL OBSERVES DYING LIVE WINDOW' in log, 'race observers not reached')
                else:
                    require(record['input_edges'] == 100, 'window queue did not receive host input')
                record['passed'] = True
                record['completed_rounds'] = 102 if mode == 'lifecycle' else 1
                return record
            if pixel[0:2] == (1, 0) and (not record['rounds'] or pixel[2] != record['rounds'][-1]['round']):
                record['rounds'].append({'round': pixel[2], 'elapsed': time.monotonic() - start})
            if mode == 'queue' and pixel == (0, 255, 255) and not sent:
                sent = True
                # One edge per SYN frame; 100 exceeds per-window capacity64,
                # while paced desktop routing keeps the raw queue below its cap.
                for edge in range(100):
                    qmp.input([{'type': 'key', 'data': {'down': edge % 2 == 0,
                               'key': {'type': 'qcode', 'data': 'a'}}}])
                    record['input_edges'] += 1
                    time.sleep(.02)
            time.sleep(.05)
        raise AssertionError('protected lifecycle/queue deadline expired')
    finally:
        record['elapsed'] = time.monotonic() - start
        if qmp:
            (target / 'qmp.json').write_text(json.dumps(qmp.log, indent=2) + '\n')
        process.terminate()
        _, error = process.communicate(timeout=5)
        (target / 'stderr.log').write_bytes(error)
        (target / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--mode', choices=['lifecycle', 'queue'], default='lifecycle')
    parser.add_argument('--kernel-from', type=Path)
    parser.add_argument('--reproduce-old-kill', action='store_true',
                        help='Negative control only: remove the Dying/Exited fix in the frozen snapshot')
    args = parser.parse_args()
    out, compiler = args.out.resolve(), args.compiler.resolve()
    record = {'passed': False, 'compiler_sha256': sha(compiler), 'firmware_sha256': sha(FIRMWARE),
              'mode': args.mode, 'source_inputs': kernel_probe.snapshot(out)}
    try:
        observe(out)
        if args.reproduce_old_kill:
            path = out / 'kernel/dispatch_window.vt'
            text = path.read_text()
            start = text.index('                match process::state(target) {', text.index('unsafe fn desktop_kill'))
            end = text.index('                if !process::terminate(target, abi::CANCELLED)', start)
            path.write_text(text[:start] + text[end:])
            record['negative_control'] = 'old DesktopKill expected panic23; never a production candidate'
        command = kernel_probe.build(compiler, out, programs(args.mode), record,
                                     args.kernel_from.resolve() if args.kernel_from else None)
        initial = out / 'initial'
        for name in ['sys', 'work', 'jobs']:
            (initial / name).mkdir(parents=True)
        result = subprocess.run(['python3', str(ROOT / 'tools/mkfs.py'), '--contract',
                                 str(out / 'abi/contract.vt'), str(initial), str(out / 'disk.raw')], capture_output=True)
        (out / 'mkfs.log').write_bytes(result.stdout + result.stderr)
        require(result.returncode == 0, 'mkfs failed')
        command += ['-display', 'none', '-global', 'virtio-mmio.force-legacy=false',
                    '-device', 'virtio-keyboard-device', '-device', 'virtio-tablet-device',
                    '-drive', f'file={out}/disk.raw,if=none,format=raw,id=blk,cache=writeback',
                    '-device', 'virtio-blk-device,drive=blk']
        record['run'] = command
        record['result'] = run(out, command, args.mode)
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Protected K5 lifecycle gate passed:', args.mode)


if __name__ == '__main__':
    main()
