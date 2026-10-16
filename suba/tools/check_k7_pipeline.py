#!/usr/bin/env python3
"""Run unchanged native build worker/compiler through a protected U controller."""
import argparse
import json
from pathlib import Path
import shutil
import build_users
import kernel_probe
from check_k2 import sha
from check_k7_kernel import run
from mkfs import format_disk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--invalid', action='store_true')
    args = parser.parse_args()
    compiler, system, out = args.compiler.resolve(), args.system.resolve(), args.out.resolve()
    previous = json.loads((system / 'verification.json').read_text())
    assert previous['built'], 'system snapshot not built'
    record = {'passed': False, 'seed_compiler_sha256': sha(compiler), 'system': str(system),
              'source_inputs': kernel_probe.snapshot(out), 'invalid': args.invalid}
    sources = build_users.COMMON + ['user/build/io.vt', 'biomiya/compiler/runtime/bytes.vt', 'tests/k7/build_probe.vt']
    for name in sources:
        target = out / name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(build_users.source_path(name), target)
    program = dict(entry='test::build_pipeline::' + ('invalid' if args.invalid else 'main'),
                   sources=sources, assembly=['user/libsuba/syscall.s0'])
    try:
        command = kernel_probe.build(compiler, out, [program], record, system)
        tree = out / 'initial'
        for name in ('sys', 'work', 'jobs'):
            (tree / name).mkdir(parents=True)
        for name in ('build', 'compiler'):
            artifact = system / 'build' / (name + '.elf')
            assert sha(artifact) == previous['programs'][name]['sha256']
            record['guest_' + name + '_sha256'] = sha(artifact)
            shutil.copyfile(artifact, tree / 'sys' / (name + '.elf'))
        for name in ('hello.vt', 'program.build', 'syscall.s0'):
            shutil.copyfile(system / 'initial/work' / name, tree / 'work' / name)
        if args.invalid:
            fake = build_users.build(compiler, out, 'invalid-compiler', 'test::build_pipeline::bad_compiler', sources, record)
            shutil.copyfile(fake, tree / 'sys/compiler.elf')
            (tree / 'work/hello.elf').write_bytes(b'previous complete publication')
        record['initial_disk'] = format_disk(tree, out / 'disk.raw', out / 'abi/contract.vt')
        command += ['-global', 'virtio-mmio.force-legacy=false', '-device', 'virtio-keyboard-device',
                    '-device', 'virtio-tablet-device', '-drive',
                    f'file={out}/disk.raw,if=none,format=raw,id=blk,cache=writeback',
                    '-device', 'virtio-blk-device,drive=blk']
        record['result'] = run(out, command)
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K7 real pipeline passed', 'invalid-output' if args.invalid else 'build-run-fail-cancel')


if __name__ == '__main__':
    main()
