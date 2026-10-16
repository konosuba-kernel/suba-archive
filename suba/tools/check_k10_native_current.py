#!/usr/bin/env python3
"""Rebuild final current kernel in guest; compare clean seed build; transport and run."""
import argparse
import json
from pathlib import Path
import shutil
import build_users
import kernel_probe
import native_probe
import ram_launch
from check_k2 import sha
from mkfs import format_disk
from read_disk import Disk

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--system', type=Path, required=True, help='fresh final production build')
    parser.add_argument('--native-compiler', type=Path, required=True, help='accepted K8 C3')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=2400)
    args = parser.parse_args()
    compiler, system, out = args.compiler.resolve(), args.system.resolve(), args.out.resolve()
    prior = json.loads((system / 'verification.json').read_text())
    record = {'passed': False, 'system_report_sha256': sha(system / 'verification.json'),
              'compiler_sha256': sha(compiler), 'source_inputs': kernel_probe.snapshot(out)}
    try:
        sources = build_users.COMMON + ['user/build/io.vt', 'biomiya/compiler/runtime/bytes.vt',
                                      'tests/k8/native.vt', 'tests/k9/native.vt', 'tests/k10/native_current.vt']
        for name in sources:
            target = out / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(build_users.source_path(name), target)
        programs = [dict(entry=entry, sources=sources, assembly=['user/libsuba/syscall.s0'])
                    for entry in ('test::current_native::main', 'test::kernel_native::after')]
        command = kernel_probe.build(compiler, out, programs, record, system)
        tree = out / 'initial'
        shutil.copytree(system / 'initial', tree)
        assert sha(args.native_compiler) == prior['programs']['compiler']['sha256']
        shutil.copyfile(args.native_compiler, tree / 'sys/compiler.elf')
        # Bind the editable manifest to every input of the clean production ELF.
        actual = []
        for line in (tree / 'work/kernel.build').read_text().splitlines():
            if line.startswith(('source ', 'assembly ')):
                name = line.split(' ', 1)[1]
                relative = name.removeprefix('system/')
                assert name.startswith('system/')
                assert (tree / 'work' / name).read_bytes() == (system / relative).read_bytes()
                actual.append(relative)
        expected = [line.split(' ', 1)[1] for line in (system / 'kernel/kernel.build').read_text().splitlines()
                    if line.startswith(('source ', 'assembly '))]
        assert actual == expected
        assert len([name for name in actual if name.endswith(".vt")]) == 64
        assert "kernel/dispatch_power.vt" in actual
        assert sha(system / 'build/kernel.elf') == prior['kernel']['sha256']
        (tree / 'work/hello.build').write_bytes((tree / 'work/program.build').read_bytes())
        record['initial_disk'] = format_disk(tree, out / 'disk.raw', out / 'abi/contract.vt')
        record['native'] = native_probe.run(out, native_probe.devices(command, out / 'disk.raw'), args.seconds)
        disk = Disk(out / 'disk.raw', out / 'abi/contract.vt')
        exported = out / 'exported'
        exported.mkdir()
        for name in ('kernel.elf', 'current.log'):
            (exported / name).write_bytes(disk.read('/work/' + name))
        guest = exported / 'kernel.elf'
        assert guest.read_bytes() == (system / 'build/kernel.elf').read_bytes()
        record['full_byte_equal_clean_host_build'] = True
        record['native_kernel_sha256'] = sha(guest)
        deployed = out / 'boot-current'
        launch = ram_launch.prepare(system / 'build/ram-boot.elf', guest, out / 'build/user1.elf',
                                    out / 'disk.raw', deployed, sha(guest))
        ram_launch.validate(deployed)
        record['new_kernel'] = native_probe.run(deployed, launch, args.seconds)
        after = Disk(deployed / 'disk.raw', out / 'abi/contract.vt')
        assert after.read('/work/kernel.elf') == guest.read_bytes() == (deployed / 'kernel.elf').read_bytes()
        assert after.read('/work/hello.elf').startswith(b'\x7fELF')
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Final current native kernel matches clean build, boots and compiles an application')


if __name__ == '__main__':
    main()
