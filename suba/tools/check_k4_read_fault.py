#!/usr/bin/env python3
"""Distinguish guest FileRead EIO from a write's internal edge-block read."""
import argparse
import json
from pathlib import Path
import shutil
from check_k4_faults import digest, run_case
from kernel_probe import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-from', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source, out, compiler = args.kernel_from.resolve(), args.out.resolve(), args.compiler.resolve()
    previous = json.loads((source / 'verification.json').read_text())
    assert previous['passed'] and previous['case'] == 'filesystem'
    assert previous['compiler_sha256'] == digest(compiler)
    out.mkdir(parents=True, exist_ok=False)
    fixture = out / 'fixture'
    fixture.mkdir()
    (fixture / 'build').mkdir()
    for name, expected in previous['compiled_inputs'].items():
        assert digest(source / name) == expected
        target = fixture / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    for name in ('tests/k0/boot.vt', 'tests/k0/fw_cfg.vt'):
        target = fixture / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    sources = ['abi/contract.vt', 'abi/syscalls.vt', 'abi/argument_wire.vt',
               'user/libsuba/syscall.vt', 'abi/files.vt', 'user/libsuba/files.vt',
               'tests/k4/faults/read.vt']
    record = dict(compiler_sha256=digest(compiler), source_report_sha256=digest(source / 'verification.json'),
                  passed=False)
    try:
        command = build(compiler, fixture, [dict(entry='test::program::run', sources=sources,
                        assembly=['user/libsuba/syscall.s0'])], record, source)
        command += ['-global', 'virtio-mmio.force-legacy=false', '-drive', 'replaced',
                    '-device', 'virtio-blk-device,drive=blk']
        record['healthy'] = run_case(command, out, 'healthy_read', None,
                                    contract=source / 'abi/contract.vt')
        record['fault'] = run_case(command, out, 'file_read_eio', 71, ('read_aio', 193 * 8),
                                  source / 'abi/contract.vt')
        record['passed'] = record['healthy']['passed'] and record['fault']['passed']
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    assert record['passed'], 'see logs'
    print('Guest FileRead healthy control and EIO panic passed')


if __name__ == '__main__':
    main()
