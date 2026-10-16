#!/usr/bin/env python3
"""Run K4 storage regressions on the integrated K5 kernel.

The storage fixture is an ordinary boot process, not a desktop. Only its test
snapshot disables the boot desktop grant; production boot policy is unchanged.
Real keyboard/tablet devices remain present and serviced by the K5 IRQ hub.
All K4 assertions and per-input kernel-reuse checks remain in force.
"""
import json
from pathlib import Path
import sys

import check_k4
from check_k2 import sha

snapshot_kernel = check_k4.snapshot
build_kernel = check_k4.build
output = None


def snapshot(out):
    global output
    output = out
    inputs = snapshot_kernel(out)
    path = out / 'kernel/dispatch_spawn.vt'
    text = path.read_text()
    anchor = 'return boot_process(id, bytes, index == 0_usize);'
    assert text.count(anchor) == 1, 'K5 ordinary storage fixture boot anchor'
    path.write_text(text.replace(anchor, 'return boot_process(id, bytes, false);'))
    return inputs


def build(*args, **kwargs):
    command = build_kernel(*args, **kwargs)
    return command + ['-device', 'virtio-keyboard-device', '-device', 'virtio-tablet-device']


if __name__ == '__main__':
    check_k4.snapshot = snapshot
    check_k4.build = build
    try:
        check_k4.main()
    finally:
        if output and (output / 'verification.json').exists():
            path = output / 'verification.json'
            record = json.loads(path.read_text())
            record['k5_adapter'] = {'sha256': sha(Path(__file__)),
                                    'boot_fixture': 'ordinary process, no Desktop grant',
                                    'devices': ['virtio-keyboard-device', 'virtio-tablet-device']}
            path.write_text(json.dumps(record, indent=2) + '\n')
