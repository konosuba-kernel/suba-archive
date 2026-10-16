#!/usr/bin/env python3
"""Real fixed-profile boot rejection cases; no guest state or ELF patching."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from check_kernel_entry import observe, require
from check_k2 import sha
import ram_launch


def without_device(command, prefix):
    result = []
    i = 0
    found = False
    while i < len(command):
        if command[i] == '-device' and command[i + 1].startswith(prefix):
            found = True
            i += 2
        else:
            result.append(command[i])
            i += 1
    require(found, 'missing original device ' + prefix)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source = args.deployment.resolve()
    description = json.loads((source / 'deployment.json').read_text())
    for name, item in description['products'].items():
        # The disk may legitimately have changed during its completed previous boot.
        if name != 'disk.raw':
            require(sha(source / name) == item['sha256'], 'deployment changed: ' + name)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = {'passed': False, 'source': str(source), 'deployment': description,
              'qemu_version': subprocess.check_output(['qemu-system-riscv64', '--version'], text=True), 'cases': []}
    try:
        for name in ('missing-block', 'missing-keyboard', 'missing-tablet', 'missing-ramfb', 'legacy-transport', 'wrong-ram'):
            work = out / name
            work.mkdir()
            shutil.copyfile(source / 'disk.raw', work / 'disk.raw')
            command = [arg.replace('file=' + str(source / 'disk.raw') + ',', 'file=' + str(work / 'disk.raw') + ',')
                       for arg in description['command']]
            if name.startswith('missing-'):
                prefix = {'missing-block': 'virtio-blk-device', 'missing-keyboard': 'virtio-keyboard-device',
                          'missing-tablet': 'virtio-tablet-device', 'missing-ramfb': 'ramfb'}[name]
                command = without_device(command, prefix)
            if name == 'legacy-transport':
                command[command.index('virtio-mmio.force-legacy=false')] = 'virtio-mmio.force-legacy=true'
            if name == 'wrong-ram':
                command[command.index('-m') + 1] = '256M'
            command += ['-display', 'none', '-monitor', 'none']
            result = observe(command, 'panic', ['suba K3: root exit'], timeout=30)
            (work / 'serial.log').write_text(result.pop('log'))
            result['case'] = name
            record['cases'].append(result)
            require(result['passed'], 'guest did not reject platform case ' + name)
            print(name, 'controlled guest rejection', flush=True)
        # Firmware identity belongs to the host launch boundary. Corrupt only a
        # copied manifest, never the installed firmware or a guest disk.
        work = out / 'wrong-firmware-identity'
        work.mkdir()
        for name in ('boot.elf', 'kernel.elf', 'desktop.elf', 'start.bin'):
            shutil.copyfile(source / name, work / name)
        altered = dict(description)
        altered['firmware_sha256'] = '0' * 64
        (work / 'deployment.json').write_text(json.dumps(altered, indent=2) + '\n')
        try:
            ram_launch.validate(work)
        except ValueError as error:
            require('firmware changed' in str(error), 'unexpected firmware rejection')
            record['cases'].append({'case': 'wrong-firmware-identity', 'passed': True,
                                    'boundary': 'host launcher; no guest started', 'reason': str(error)})
        else:
            raise AssertionError('wrong firmware identity accepted')
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
