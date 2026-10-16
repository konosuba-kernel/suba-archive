#!/usr/bin/env python3
"""Shared native-build observer: no host writes to guest files after launch."""
import json
import hashlib
import platform
from pathlib import Path
import subprocess
import time
from PIL import Image
from check_k5_devices import Qmp
from check_kernel_entry import require


def devices(command, disk):
    return command + ['-global', 'virtio-mmio.force-legacy=false',
        '-device', 'virtio-keyboard-device', '-device', 'virtio-tablet-device',
        '-drive', f'file={disk},if=none,format=raw,id=blk,cache=writeback',
        '-device', 'virtio-blk-device,drive=blk']


def run(out, command, seconds=3600):
    command = [item for item in command if item != '-nographic']
    command += ['-display', 'none', '-serial', 'file:' + str(out / 'serial.log'),
        '-monitor', 'none', '-qmp', 'unix:' + str(out / 'qmp.sock') + ',server=on,wait=off']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    start = time.monotonic()
    qmp = None
    firmware = Path(command[command.index('-bios') + 1])
    record = {'passed': False, 'command': command, 'stages': [], 'deadline_seconds': seconds,
              'qemu_version': subprocess.check_output([command[0], '--version'], text=True),
              'firmware_sha256': hashlib.sha256(firmware.read_bytes()).hexdigest(),
              'host': platform.platform()}
    cpuinfo = Path('/proc/cpuinfo')
    if cpuinfo.exists():
        record['host_cpu'] = next((line.split(':', 1)[1].strip() for line in cpuinfo.read_text().splitlines()
                                   if line.startswith('model name')), 'unknown')
    try:
        while not (out / 'qmp.sock').exists():
            require(process.poll() is None and time.monotonic() - start < 30, 'QMP startup failed')
            time.sleep(.05)
        qmp = Qmp(out / 'qmp.sock')
        previous = None
        while time.monotonic() - start < seconds:
            require(process.poll() is None, 'QEMU exited before result')
            log = (out / 'serial.log').read_text() if (out / 'serial.log').exists() else ''
            require('panic' not in log.lower(), log[-4000:])
            qmp.call('screendump', {'filename': str(out / 'frame.ppm')})
            frame = Image.open(out / 'frame.ppm')
            pixels = [frame.getpixel((i, 0)) for i in range(5)]
            current = tuple(pixels)
            if current != previous:
                record['stages'].append({'elapsed': time.monotonic() - start, 'pixels': pixels})
                frame.save(out / ('stage-' + str(len(record['stages'])) + '.png'))
                (out / 'progress.json').write_text(json.dumps(record, indent=2) + '\n')
                print(json.dumps(record['stages'][-1]), flush=True)
                previous = current
            require(pixels[0][0] != 255, 'native guest assertion: ' + str(pixels))
            if pixels[0] == (0, 255, 0):
                record['passed'] = True
                return record
            time.sleep(.5)
        raise AssertionError('native guest deadline exceeded')
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        record['elapsed'] = time.monotonic() - start
        process.terminate()
        _, error = process.communicate(timeout=10)
        (out / 'stderr.log').write_bytes(error)
        if qmp:
            (out / 'qmp.json').write_text(json.dumps(qmp.log, indent=2) + '\n')
        (out / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
