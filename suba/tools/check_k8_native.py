#!/usr/bin/env python3
"""Native C0 -> C1 -> C2 -> C3, guest source mutation, full-byte host oracle."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import build_users
import kernel_probe
import native_probe
from check_k2 import sha
from mkfs import format_disk
from read_disk import Disk

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--system', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--kernel-from', type=Path)
    parser.add_argument('--seconds', type=int, default=3600)
    args = parser.parse_args()
    compiler, system, out = args.compiler.resolve(), args.system.resolve(), args.out.resolve()
    previous = json.loads((system / 'verification.json').read_text())
    record = {'passed': False, 'compiler_sha256': sha(compiler), 'system': str(system),
              'source_inputs': kernel_probe.snapshot(out)}
    try:
        sources = build_users.COMMON + ['user/build/io.vt', 'biomiya/compiler/runtime/bytes.vt', 'tests/k8/native.vt']
        for name in sources:
            target = out / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(build_users.source_path(name), target)
        program = dict(entry='test::native::main', sources=sources, assembly=['user/libsuba/syscall.s0'])
        command = kernel_probe.build(compiler, out, [program], record,
                                     args.kernel_from.resolve() if args.kernel_from else system)
        tree = out / 'initial'
        for name in ('sys', 'work', 'jobs'):
            (tree / name).mkdir(parents=True)
        seed = system / 'build/compiler.elf'
        assert sha(seed) == previous['programs']['compiler']['sha256']
        record['c0_sha256'] = sha(seed)
        shutil.copyfile(seed, tree / 'sys/compiler.elf')
        names = build_users.compiler_sources()
        for name in names + ['user/libsuba/syscall.s0']:
            source = build_users.source_path(name)
            # C0 must describe exactly the sources being rebuilt, including host_suba.
            assert sha(source) == previous['programs']['compiler']['inputs'][name], name
            target = tree / 'work' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        record['native_inputs'] = {name: sha(tree / 'work' / name) for name in names + ['user/libsuba/syscall.s0']}
        lines = ['format 1', 'profile suba-user', 'entry bootstrap::main::run']
        lines += ['source ' + name for name in names] + ['assembly user/libsuba/syscall.s0']
        for name in ('c1', 'c2', 'c3', 'mutant'):
            (tree / 'work' / (name + '.build')).write_text('\n'.join(lines + ['output ' + name + '.elf']) + '\n')
        (tree / 'work/hello.vt').write_text('module demo; pub fn main() -> u32 { return 41; }\n')
        (tree / 'work/hello.build').write_text('format 1\nprofile suba-user\nentry demo::main\nsource hello.vt\nassembly user/libsuba/syscall.s0\noutput hello.elf\n')
        record['initial_disk'] = format_disk(tree, out / 'disk.raw', out / 'abi/contract.vt')
        record['result'] = native_probe.run(out, native_probe.devices(command, out / 'disk.raw'), args.seconds)
        disk = Disk(out / 'disk.raw', out / 'abi/contract.vt')
        exported = out / 'exported'
        exported.mkdir()
        for name in ('c1.elf', 'c2.elf', 'c3.elf', 'mutant.elf', 'hello.elf', 'c1.log', 'c2.log', 'c3.log', 'mutant.log', 'hello.log', 'before.log', 'after.log'):
            (exported / name).write_bytes(disk.read('/work/' + name))
        record['products'] = {path.name: {'sha256': sha(path), 'bytes': path.stat().st_size} for path in exported.iterdir()}
        assert all((exported / name).read_bytes() == seed.read_bytes() for name in ('c1.elf', 'c2.elf', 'c3.elf'))
        assert (exported / 'mutant.elf').read_bytes() != seed.read_bytes()
        oracle = out / 'oracle'
        shutil.copytree(tree / 'work', oracle)
        # The only changed source is read back from the stopped disk, then used by
        # the Linux-host compiler; it never supplies bytes to the live guest.
        changed = disk.read('/work/biomiya/compiler/main.vt')
        original = (oracle / 'biomiya/compiler/main.vt').read_bytes()
        assert changed == original.replace(b'return 2;', b'return 7;', 1)
        (exported / 'main.vt').write_bytes(changed)
        for name in ('c1', 'hello', 'mutant'):
            if name == 'mutant':
                (oracle / 'biomiya/compiler/main.vt').write_bytes(changed)
            cmd = ['qemu-riscv64', '-s', '1048576', str(compiler), 'build', name + '.build']
            result = subprocess.run(cmd, cwd=oracle, capture_output=True, timeout=600)
            (out / (name + '-oracle.log')).write_bytes(result.stdout + result.stderr)
            assert result.returncode == 0
            assert (oracle / (name + '.elf')).read_bytes() == (exported / (name + '.elf')).read_bytes(), name
        record['host_full_byte_equal'] = ['c1', 'hello', 'mutant']
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K8 native fixed point and mutation passed')


if __name__ == '__main__':
    main()
