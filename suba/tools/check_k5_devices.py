#!/usr/bin/env python3
"""Build unchanged K5 display/input owners and exercise real IRQ/QMP/GTK input.

This is a bare supervisor driver probe. Only the test platform alias is zero;
protection, applications and full K5 acceptance belong to check_k5 integration.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import select
import subprocess
import time
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = Path('/usr/share/qemu/opensbi-riscv64-generic-fw_dynamic.bin')
FILES = ['abi/contract.vt', 'abi/windows.vt', 'platform/devices.vt',
         'kernel/device/display.vt', 'kernel/device/input.vt', 'kernel/device/io.vt',
         'kernel/device/io.s0', 'kernel/device/virtio.vt', 'kernel/machine.vt',
         'kernel/machine.s0', 'tests/k4/transport/irq.s0',
         'tests/k5/device_probe.vt', 'tests/k5/device_probe.s0', 'tests/k5/gtk_input.py']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Qmp:
    def __init__(self, path):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.connect(str(path))
        self.stream = self.socket.makefile('rwb', buffering=0)
        self.log = [json.loads(self.stream.readline())]
        self.call('qmp_capabilities')

    def call(self, name, arguments=None):
        message = {'execute': name}
        if arguments is not None:
            message['arguments'] = arguments
        self.log.append({'request': message})
        self.stream.write((json.dumps(message) + '\n').encode())
        while True:
            result = json.loads(self.stream.readline())
            self.log.append(result)
            if 'error' in result:
                raise AssertionError(result)
            if 'return' in result:
                return result['return']

    def input(self, events):
        self.call('input-send-event', {'events': events})
        time.sleep(.1)


@contextmanager
def x11_server(binary, directory):
    """Own a private X server; no user desktop focus or Wayland input emulation."""
    read_fd, write_fd = os.pipe()
    command = [str(binary), '-displayfd', str(write_fd), '-screen', '0',
               '1280x1024x24', '-nolisten', 'tcp', '-r']
    (directory / 'xvfb-command.json').write_text(json.dumps(command, indent=2) + '\n')
    with (directory / 'xvfb.log').open('wb') as log:
        process = subprocess.Popen(command, pass_fds=(write_fd,), stdout=log, stderr=log)
        os.close(write_fd)
        try:
            if not select.select([read_fd], [], [], 10)[0]:
                raise AssertionError('private X11 server did not become ready')
            display = os.read(read_fd, 100).decode().strip()
            assert display.isdigit(), 'private X11 server exited without a display'
            yield ':' + display
        finally:
            os.close(read_fd)
            process.terminate()
            process.wait(timeout=5)


def run(out, gtk, display=None):
    directory = out / ('gtk' if gtk else 'qmp')
    directory.mkdir()
    sock = directory / 'qmp.sock'
    serial = directory / 'serial.log'
    command = ['qemu-system-riscv64', '-machine', 'virt', '-m', '512M', '-smp', '1',
               '-bios', str(FIRMWARE), '-kernel', str(out / 'probe.elf'),
               '-device', 'ramfb', '-device', 'virtio-keyboard-device',
               '-device', 'virtio-tablet-device', '-global', 'virtio-mmio.force-legacy=false',
               '-display', 'gtk' if gtk else 'none', '-name', 'k5-driver',
               '-serial', 'file:' + str(serial), '-monitor', 'none', '-qmp',
               'unix:' + str(sock) + ',server=on,wait=off']
    environment = os.environ.copy()
    if gtk:
        environment['GDK_BACKEND'] = 'x11'
        if display is not None:
            environment['DISPLAY'] = display
            environment.pop('WAYLAND_DISPLAY', None)
    (directory / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    qmp = None
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError('QEMU exited before driver readiness')
            if sock.exists() and serial.exists() and 'K5 DEVICE READY' in serial.read_text():
                break
            time.sleep(.05)
        else:
            raise AssertionError('driver initialization timed out')
        qmp = Qmp(sock)
        if gtk:
            # Kernel readiness can precede GTK's map/focus setup; allow its initial
            # window events to settle before operating the actual client surface.
            time.sleep(1)
            injected = subprocess.run(['python3', str(out / 'tests/k5/gtk_input.py'), 'k5-driver'],
                                      capture_output=True, timeout=15, env=environment)
            (directory / 'injection.log').write_bytes(injected.stdout + injected.stderr)
            assert injected.returncode == 0, injected.stderr
            time.sleep(.4)
        else:
            for down in [True, False]:
                qmp.input([{'type': 'key', 'data': {'down': down, 'key': {'type': 'qcode', 'data': 'a'}}}])
            qmp.input([{'type': 'abs', 'data': {'axis': 'x', 'value': 16000}},
                       {'type': 'abs', 'data': {'axis': 'y', 'value': 16000}}])
            for down in [True, False]:
                qmp.input([{'type': 'btn', 'data': {'down': down, 'button': 'left'}}])
        qmp.call('screendump', {'filename': str(directory / 'frame.ppm')})
        image = Image.open(directory / 'frame.ppm')
        image.save(directory / 'frame.png')
        assert image.size == (1024, 768)
        assert [image.getpixel(point) for point in [(25, 25), (45, 25), (65, 25)]] == [
            (0, 255, 0), (255, 0, 0), (255, 255, 0)]
        log = serial.read_text()
        assert 'PANIC' not in log
        events = [[int(word, 16) for word in line.split()[1:]]
                  for line in log.splitlines() if line.startswith('EVENT ')]
        assert any(e[0:3] == [1, 30, 1] for e in events)
        assert any(e[0:3] == [1, 30, 0] for e in events)
        assert any(e[0] == 2 and e[3] == 1 for e in events)
        assert any(e[0] == 2 and e[3] == 0 for e in events)
        assert max(e[4] for e in events) > 0
        return {'kind': ('GTK/XTest/private-X11' if display else 'GTK/XTest/session-X11') if gtk else 'QMP', 'events': events,
                'serial_sha256': sha(serial), 'frame_sha256': sha(directory / 'frame.png')}
    finally:
        if qmp is not None:
            (directory / 'qmp.json').write_text(json.dumps(qmp.log, indent=2) + '\n')
        process.terminate()
        output, error = process.communicate(timeout=5)
        (directory / 'stderr.log').write_bytes(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--gtk', action='store_true')
    parser.add_argument('--xvfb', type=Path, help='Use this private Xvfb binary for the GTK test')
    args = parser.parse_args()
    out = args.out.resolve()
    compiler = args.compiler.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = {'scope': 'bare S driver IRQ probe, not complete K5', 'passed': False,
              'compiler_sha256': sha(compiler), 'firmware_sha256': sha(FIRMWARE), 'inputs': {}}
    for name in FILES:
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        record['inputs'][name] = sha(target)
    platform = out / 'platform/devices.vt'
    text = platform.read_text()
    assert text.count('0x40000000') == 1
    platform.write_text(text.replace('0x40000000', '0x00000000'))
    record['test_platform_sha256'] = sha(platform)
    manifest = ['format 1', 'profile suba-kernel', 'entry test::k5_device::start',
                'bind panic=test::k5_device::panic', 'bind trap_dispatch=test::k5_device::handle']
    manifest += ['source ' + name for name in FILES if name.endswith('.vt')]
    manifest += ['assembly ' + name for name in FILES if name.endswith('.s0')]
    manifest += ['output probe.elf']
    (out / 'probe.build').write_text('\n'.join(manifest) + '\n')
    try:
        compiled = subprocess.run(['qemu-riscv64', '-s', '1048576', str(compiler), 'build', 'probe.build'],
                                  cwd=out, capture_output=True, timeout=120)
        (out / 'compile.log').write_bytes(compiled.stdout + compiled.stderr)
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr
        record['elf_sha256'] = sha(out / 'probe.elf')
        record['runs'] = [run(out, False)]
        if args.gtk:
            if args.xvfb:
                record['xvfb_sha256'] = sha(args.xvfb.resolve())
                with x11_server(args.xvfb.resolve(), out) as display:
                    record['runs'].append(run(out, True, display))
            else:
                record['runs'].append(run(out, True))
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K5 driver IRQ paths passed:', ', '.join(item['kind'] for item in record['runs']))


if __name__ == '__main__':
    main()
