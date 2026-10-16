#!/usr/bin/env python3
"""Freeze the integrated production kernel and build protected K5 fixtures.

The only observer changes boot two ordinary test images after the real trusted
U desktop and prints resource counters after root collection. No ELF patching,
host-served runtime files or management permission bypass occurs.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
from check_k2 import sha
from check_kernel_entry import FIRMWARE, require
import kernel_probe
from check_k5_desktop import run as desktop_run
from check_k5_devices import x11_server

ROOT = Path(__file__).resolve().parents[1]


def observe(out):
    entry = out / 'kernel/entry.vt'
    text = entry.read_text()
    anchor = '        let frame: usize = schedule();'
    require(text.count(anchor) == 1, 'K5 entry observer anchor')
    text = text.replace(anchor, '''        machine::text("K5 BASELINE ");
        dispatch::number(memory::stats().free); machine::text("\\n");
        if !dispatch::boot(1) || !dispatch::boot(2) { return panic(21); }
        machine::text("K5 PROTECTED DESKTOP READY\\n");
''' + anchor)
    entry.write_text(text)
    dispatch = out / 'kernel/dispatch.vt'
    text = dispatch.read_text()
    anchor = 'machine::text("suba K3: root exit "); number(exit.status); machine::text("\\n");'
    require(text.count(anchor) == 1, 'K5 root collection observer anchor')
    text = text.replace(anchor, anchor + '''
                                        machine::text("K5 REAP free="); number(memory::stats().free);
                                        machine::text(" surfaces="); number(window::surface_pages());
                                        machine::text("\\n");''')
    dispatch.write_text(text)


def programs(mode):
    lines = (ROOT / 'user/desktop/desktop.build').read_text().splitlines()
    sources = [line.split(' ', 1)[1] for line in lines if line.startswith('source ')]
    assembly = ['user/libsuba/syscall.s0']
    desktop = dict(entry='user::desktop::main', sources=sources, assembly=assembly)
    common = [name for name in sources if not name.startswith(('user/desktop/', 'user/draw/'))]
    if mode == 'desktop':
        names = ['test::k5_app::green', 'test::k5_app::amber']
        common += ['tests/k5/apps.vt']
    else:
        names = ['test::k5_contracts::run', 'test::k5_contracts::forbidden_display']
        common += ['tests/k5/contracts.vt']
    return [desktop] + [dict(entry=name, sources=common, assembly=assembly) for name in names]


def contracts(out, command):
    import re
    target = out / 'contracts'
    target.mkdir()
    command = [part for part in command if part != '-nographic']
    command += ['-serial', 'file:' + str(target / 'serial.log'), '-monitor', 'none']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            require(process.poll() is None, 'QEMU exited before contract observations')
            log = (target / 'serial.log').read_text() if (target / 'serial.log').exists() else ''
            require('panic' not in log.lower(), 'kernel panicked: ' + log)
            baseline = re.findall(r'K5 BASELINE (\d+)', log)
            reaped = re.findall(r'K5 REAP free=(\d+) surfaces=(\d+)', log)
            if baseline and len(reaped) == 2 and reaped[-1] == (baseline[0], '0'):
                require('suba K3: root exit 0' in log, 'ordinary ABI fixture failed')
                require('suba K3: user fault isolated' in log, 'ordinary display mapping escaped')
                require('suba K3: root exit 99' not in log, 'forbidden display write returned')
                return {'passed': True, 'free_pages': int(baseline[0]), 'surface_pages': 0,
                        'serial_sha256': sha(target / 'serial.log')}
            time.sleep(.05)
        raise AssertionError('contract fixture/resource baseline timed out')
    finally:
        process.terminate()
        _, error = process.communicate(timeout=5)
        (target / 'stderr.log').write_bytes(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--mode', choices=['desktop', 'contracts'], default='desktop')
    parser.add_argument('--kernel-from', type=Path, help='Reuse only an identical frozen observed kernel')
    parser.add_argument('--xvfb', type=Path)
    args = parser.parse_args()
    compiler, out = args.compiler.resolve(), args.out.resolve()
    record = {'passed': False, 'compiler_sha256': sha(compiler), 'firmware_sha256': sha(FIRMWARE),
              'mode': args.mode, 'source_inputs': kernel_probe.snapshot(out)}
    try:
        require('source kernel/window.vt' in (out / 'kernel/kernel.build').read_text(),
                'K5 production core integration must precede this gate')
        observe(out)
        command = kernel_probe.build(compiler, out, programs(args.mode), record,
                                     args.kernel_from.resolve() if args.kernel_from else None)
        initial = out / 'initial'
        for name in ['sys', 'work', 'jobs']:
            (initial / name).mkdir(parents=True)
        result = subprocess.run(['python3', str(ROOT / 'tools/mkfs.py'), '--contract',
                                 str(out / 'abi/contract.vt'), str(initial), str(out / 'disk.raw')],
                                capture_output=True)
        (out / 'mkfs.log').write_bytes(result.stdout + result.stderr)
        require(result.returncode == 0, 'mkfs failed')
        command += ['-display', 'none', '-global', 'virtio-mmio.force-legacy=false',
                    '-device', 'virtio-keyboard-device', '-device', 'virtio-tablet-device',
                    '-drive', f'file={out}/disk.raw,if=none,format=raw,id=blk,cache=writeback',
                    '-device', 'virtio-blk-device,drive=blk']
        record['run'] = command
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
        if args.mode == 'contracts':
            record['contracts'] = contracts(out, command)
        else:
            target = out / 'desktop'
            target.mkdir()
            if args.xvfb:
                with x11_server(args.xvfb.resolve(), target) as display:
                    desktop_run(out, target, display)
            else:
                desktop_run(out, target)
            record['desktop'] = json.loads((target / 'verification.json').read_text())
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Integrated K5 gate passed:', args.mode)


if __name__ == '__main__':
    main()
