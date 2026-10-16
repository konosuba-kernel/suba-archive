#!/usr/bin/env python3
"""Deploy an existing complete kernel ELF by byte copying only; never compiles.

The fixed RAM boot ELF discovers kernel ranges from a checked launch descriptor.
"""
import argparse
import json
from pathlib import Path
import shutil
import struct
from check_k2 import sha
from check_kernel_entry import image, FIRMWARE, require
import native_probe

KERNEL_SOURCE = 0x88000000
DESKTOP_SOURCE = 0x8c000000
DESCRIPTOR = 0x803f0000


def prepare(boot, kernel, desktop, disk, out, expected):
    # Reject identity/range corruption before creating a deployment directory.
    inputs = [('boot.elf', boot), ('kernel.elf', kernel), ('desktop.elf', desktop), ('disk.raw', disk)]
    pinned = {name: sha(source) for name, source in inputs}
    require(pinned['kernel.elf'] == expected, 'kernel SHA256 differs from guest output identity')
    kernel_meta = image(kernel, 0x80400000, 0x4000000)
    boot_meta = image(boot, 0x80200000, 0x200000)
    desktop_meta = image(desktop, 0x10000, 0x4000000)
    for name, meta in [('kernel.elf', kernel_meta), ('boot.elf', boot_meta), ('desktop.elf', desktop_meta)]:
        require(meta['sha256'] == pinned[name], 'ELF source changed during inspection: ' + name)
    require(boot_meta['end'] <= DESCRIPTOR, 'boot overlaps launch descriptor')
    require(0 < kernel_meta['bytes'] <= 0x1000000, 'kernel exceeds filesystem file limit')
    require(0 < desktop_meta['bytes'] <= 0x4000000, 'desktop raw source too large')
    out.mkdir(parents=True, exist_ok=False)
    products = {}
    for name, source in inputs:
        target = out / name
        shutil.copyfile(source, target)
        require(sha(target) == pinned[name], 'transport source changed during copy: ' + name)
        products[name] = {'source': str(source), 'sha256': sha(target), 'bytes': target.stat().st_size}
    descriptor = bytearray(256)
    struct.pack_into('<QIIQQQ', descriptor, 0, 0x3154524154534253, 1, 256,
                     KERNEL_SOURCE, kernel_meta['bytes'], 1)
    struct.pack_into('<QQ', descriptor, 64, DESKTOP_SOURCE, desktop_meta['bytes'])
    (out / 'start.bin').write_bytes(descriptor)
    command = ['qemu-system-riscv64', '-machine', 'virt', '-m', '512M', '-smp', '1',
        '-nographic', '-bios', str(FIRMWARE), '-kernel', str(out / 'boot.elf'),
        '-device', 'ramfb', '-no-reboot',
        '-device', f'loader,file={out}/kernel.elf',
        '-device', f'loader,file={out}/kernel.elf,addr={KERNEL_SOURCE},force-raw=on',
        '-device', f'loader,file={out}/desktop.elf,addr={DESKTOP_SOURCE},force-raw=on',
        '-device', f'loader,file={out}/start.bin,addr={DESCRIPTOR},force-raw=on']
    command = native_probe.devices(command, out / 'disk.raw')
    record = {'products': products, 'kernel': kernel_meta, 'boot': boot_meta, 'desktop': desktop_meta,
              'firmware_sha256': sha(FIRMWARE), 'descriptor_sha256': sha(out / 'start.bin'), 'command': command}
    (out / 'deployment.json').write_text(json.dumps(record, indent=2) + '\n')
    return command


def validate(out):
    """Verify immutable launch artifacts again; the persistent disk may evolve."""
    record = json.loads((out / 'deployment.json').read_text())
    for name in ('boot.elf', 'kernel.elf', 'desktop.elf'):
        require(sha(out / name) == record['products'][name]['sha256'], 'deployed artifact changed: ' + name)
    require(sha(out / 'start.bin') == record['descriptor_sha256'], 'launch descriptor changed')
    require(sha(FIRMWARE) == record['firmware_sha256'], 'firmware changed since deployment')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--sha256', required=True, help='expected complete guest output SHA256')
    parser.add_argument('--desktop', type=Path, required=True)
    parser.add_argument('--disk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    command = prepare(args.boot.resolve(), args.kernel.resolve(), args.desktop.resolve(),
                      args.disk.resolve(), args.out.resolve(), args.sha256)
    command.remove('-nographic')
    command += ['-serial', 'stdio', '-monitor', 'none', '-display', 'gtk']
    (args.out / 'run.json').write_text(json.dumps(command, indent=2) + '\n')
    print('Verified byte transport; launch command in', args.out / 'run.json')


if __name__ == '__main__':
    main()
