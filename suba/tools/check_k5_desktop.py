#!/usr/bin/env python3
"""Exercise a frozen protected K5 image through QMP; no guest memory injection.

Consumes a kernel_probe build record. This does not turn an exploratory kernel
snapshot into a final K5 acceptance. All observations and failed frames survive.
"""
import argparse
import json
import os
import importlib.util
import re
from pathlib import Path
import subprocess
import time
from PIL import Image
from check_k5_devices import Qmp, sha, x11_server, ROOT

BACKGROUND = (24, 37, 50)
GREEN = (21, 128, 61)
BRIGHT = (34, 197, 94)
AMBER = (180, 83, 9)


def run(snapshot, out, display=None):
    out.mkdir(parents=True, exist_ok=True)
    source = json.loads((snapshot / 'verification.json').read_text())
    command = list(source['run'])
    if '-nographic' in command:
        command.remove('-nographic')
    command += ['-serial', 'file:' + str(out / 'serial.log'), '-monitor', 'none',
                '-qmp', 'unix:' + str(out / 'qmp.sock') + ',server=on,wait=off']
    if display is not None:
        command[command.index('-display') + 1] = 'gtk,show-menubar=off,show-tabs=off,zoom-to-fit=off'
        command += ['-name', 'k5-desktop']
    environment = os.environ.copy()
    if display is not None:
        environment.update(DISPLAY=display, GDK_BACKEND='x11')
        environment.pop('WAYLAND_DISPLAY', None)
    record = {'passed': False, 'input_path': 'GTK/XTest/private-X11' if display else 'QMP', 'snapshot': str(snapshot), 'command': command,
              'kernel_sha256': sha(snapshot / 'build/kernel.elf'), 'stages': []}
    process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    qmp = None
    gtk = None
    start = time.monotonic()

    def healthy():
        assert process.poll() is None, 'QEMU exited'
        text = (out / 'serial.log').read_text() if (out / 'serial.log').exists() else ''
        assert 'panic' not in text.lower(), text
        return text

    def expect(name, pixels, limit=90):
        began = time.monotonic()
        while time.monotonic() - began < limit:
            healthy()
            path = out / (name + '.ppm')
            qmp.call('screendump', {'filename': str(path)})
            frame = Image.open(path)
            frame.save(out / (name + '.png'))
            actual = {str(point): frame.getpixel(point) for point in pixels}
            if all(frame.getpixel(point) == color for point, color in pixels.items()):
                record['stages'].append({'name': name, 'elapsed': time.monotonic() - began,
                                         'pixels': actual, 'frame_sha256': sha(out / (name + '.png'))})
                return
            time.sleep(.25)
        raise AssertionError((name, 'pixel timeout', actual, pixels))

    def pointer(x, y):
        if gtk is not None:
            gtk.move(x + 1, y + 1)
            return
        qmp.input([{'type': 'abs', 'data': {'axis': 'x', 'value': x * 32767 // 1023}},
                   {'type': 'abs', 'data': {'axis': 'y', 'value': y * 32767 // 767}}])

    def button(down, name='left'):
        if gtk is not None:
            gtk.button(down, name)
            return
        qmp.input([{'type': 'btn', 'data': {'down': down, 'button': name}}])

    def click(x, y, name='left'):
        pointer(x, y)
        button(True, name)
        button(False, name)

    def key(down, name="a"):
        if gtk is not None:
            gtk.key(down, name)
            return
        qmp.input([{'type': 'key', 'data': {'down': down, 'key': {'type': 'qcode', 'data': name}}}])

    try:
        while time.monotonic() - start < 30:
            if 'K5 PROTECTED DESKTOP READY' in healthy() and (out / 'qmp.sock').exists():
                break
            time.sleep(.05)
        else:
            raise AssertionError('protected desktop boot timed out')
        qmp = Qmp(out / 'qmp.sock')
        if display is not None:
            spec = importlib.util.spec_from_file_location('gtk_input', ROOT / 'tests/k5/gtk_input.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            gtk = module.Input('k5-desktop', display)
            click(800, 600)
        expect('overlap', {(50, 100): GREEN, (100, 100): AMBER, (700, 700): BACKGROUND})
        click(50, 100)
        expect('raise-focus', {(100, 100): GREEN, (50, 50): (29, 78, 216)})
        key(True)
        expect('key-down', {(100, 100): BRIGHT})
        key(False)
        expect('key-up', {(100, 100): GREEN})
        pointer(80, 50)
        button(True)
        pointer(500, 200)
        button(False)
        expect('drag', {(50, 100): BACKGROUND, (100, 100): AMBER, (500, 250): GREEN})
        click(810, 200)
        expect('cooperative-close', {(500, 250): BACKGROUND, (100, 100): AMBER})
        click(410, 75)
        expect('unresponsive-close', {(100, 100): AMBER})
        click(100, 100)
        pointer(800, 600)
        for name in ['ctrl', 'alt', 'esc']:
            key(True, name)
        for name in ['esc', 'alt', 'ctrl']:
            key(False, name)
        expect('force-kill-hotkey', {(100, 100): BACKGROUND, (500, 250): BACKGROUND})
        # Pixel disappearance and actual resource reclamation are separate claims.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            log = healthy()
            baseline = re.findall(r'K5 BASELINE (\d+)', log)
            reaped = re.findall(r'K5 REAP free=(\d+) surfaces=(\d+)', log)
            if baseline and len(reaped) == 2 and reaped[-1] == (baseline[0], '0'):
                record['reclamation'] = {'free_pages': int(baseline[0]), 'surface_pages': 0}
                break
            time.sleep(.05)
        else:
            raise AssertionError(('resource ledger did not return', baseline, reaped))
        record['passed'] = True
    finally:
        record['elapsed'] = time.monotonic() - start
        if qmp is not None:
            (out / 'qmp.json').write_text(json.dumps(qmp.log, indent=2) + '\n')
        if gtk is not None:
            gtk.close()
        process.terminate()
        _, error = process.communicate(timeout=5)
        (out / 'stderr.log').write_bytes(error)
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Protected K5 desktop interactions passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--xvfb', type=Path, help='Use GTK/XTest through a private X server')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if args.xvfb:
        with x11_server(args.xvfb.resolve(), out) as display:
            run(args.snapshot.resolve(), out, display)
    else:
        run(args.snapshot.resolve(), out)


if __name__ == '__main__':
    main()
