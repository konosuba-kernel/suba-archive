#!/usr/bin/env python3
"""Guest VT/S0 edits, native full kernel build, unchanged transport, recompile app."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import build_users
import kernel_probe
import native_probe
import ram_launch
import fixed_boot
from check_k2 import sha
from mkfs import format_disk
from read_disk import Disk

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--system', required=True, type=Path)
    parser.add_argument('--kernel-from', type=Path)
    parser.add_argument('--native-compiler', type=Path, help='accepted K8 C3, byte-identical to the source-bound seed')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--seconds', type=int, default=3600)
    args = parser.parse_args()
    compiler, system, out = args.compiler.resolve(), args.system.resolve(), args.out.resolve()
    previous = json.loads((system / 'verification.json').read_text())
    record = {'passed': False, 'compiler_sha256': sha(compiler), 'system': str(system),
              'source_inputs': kernel_probe.snapshot(out)}
    try:
        sources = build_users.COMMON + ['user/build/io.vt', 'biomiya/compiler/runtime/bytes.vt',
                                      'tests/k8/native.vt', 'tests/k9/native.vt']
        for name in sources:
            target = out / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(build_users.source_path(name), target)
        programs = [dict(entry='test::kernel_native::' + name, sources=sources,
                         assembly=['user/libsuba/syscall.s0']) for name in ('main', 'after')]
        command = kernel_probe.build(compiler, out, programs, record,
                                     args.kernel_from.resolve() if args.kernel_from else system)
        # Compile the immutable generic boot before any guest output exists.
        fixed_boot.build(ROOT, compiler, out, record)
        tree = out / 'initial'
        for name in ('sys', 'work', 'jobs'):
            (tree / name).mkdir(parents=True)
        for name in ('build', 'compiler'):
            source = system / 'build' / (name + '.elf')
            if name == 'compiler' and args.native_compiler:
                source = args.native_compiler.resolve()
                record['native_compiler_origin'] = str(source)
            assert sha(source) == previous['programs'][name]['sha256']
            record['guest_' + name + '_sha256'] = sha(source)
            shutil.copyfile(source, tree / 'sys' / (name + '.elf'))
        kernel_lines = (out / 'kernel/kernel.build').read_text().splitlines()
        names = [line.split(' ', 1)[1] for line in kernel_lines if line.startswith(('source ', 'assembly '))]
        for name in names + ['user/libsuba/syscall.s0']:
            target = tree / 'work' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out / name, target)
        lines = [line for line in kernel_lines if not line.startswith('output ')]
        for name in ('vt', 's0'):
            (tree / 'work' / (name + '.build')).write_text('\n'.join(lines + ['output ' + name + '.elf']) + '\n')
        (tree / 'work/hello.vt').write_text('module demo; pub fn main() -> u32 { return 41; }\n')
        (tree / 'work/hello.build').write_text('format 1\nprofile suba-user\nentry demo::main\nsource hello.vt\nassembly user/libsuba/syscall.s0\noutput hello.elf\n')
        record['initial_disk'] = format_disk(tree, out / 'disk.raw', out / 'abi/contract.vt')
        record['native_build'] = native_probe.run(out, native_probe.devices(command, out / 'disk.raw'), args.seconds)
        disk = Disk(out / 'disk.raw', out / 'abi/contract.vt')
        exported = out / 'exported'
        exported.mkdir()
        for name in ('vt.elf', 's0.elf', 'vt.log', 's0.log', 'kernel/entry.vt', 'kernel/machine.s0'):
            target = exported / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(disk.read('/work/' + name))
        # Preserve actual publication records, not a host-reconstructed manifest.
        for name in disk.paths:
            if name.startswith('/work/.suba-records/') and disk.nodes[disk.paths[name]]['kind'] == 1:
                target = exported / name.removeprefix('/work/')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(disk.read(name))
        record['products'] = {str(path.relative_to(exported)): sha(path) for path in exported.rglob('*') if path.is_file()}
        assert (exported / 'kernel/entry.vt').read_bytes() == (tree / 'work/kernel/entry.vt').read_bytes().replace(
            b'suba kernel K0: handoff accepted', b'suba native V9: handoff accepted', 1)
        assert (exported / 'kernel/machine.s0').read_bytes() == (tree / 'work/kernel/machine.s0').read_bytes().replace(
            b'sb x10, 0(x5)', b'addi x6, x0, 75\nbne x10, x6, .native_plain\naddi x10, x0, 76\n.native_plain:\nsb x10, 0(x5)', 1)
        # Host oracle is kept separate; only exported guest ELFs enter deployment.
        oracle = out / 'oracle'
        shutil.copytree(tree / 'work', oracle)
        shutil.copyfile(exported / 'kernel/entry.vt', oracle / 'kernel/entry.vt')
        record['deployments'] = {}
        for name in ('vt', 's0'):
            if name == 's0':
                shutil.copyfile(exported / 'kernel/machine.s0', oracle / 'kernel/machine.s0')
            built = subprocess.run(['qemu-riscv64', '-s', '1048576', str(compiler), 'build', name + '.build'],
                                   cwd=oracle, capture_output=True, timeout=600)
            (out / (name + '-oracle.log')).write_bytes(built.stdout + built.stderr)
            assert built.returncode == 0
            guest = exported / (name + '.elf')
            assert guest.read_bytes() == (oracle / (name + '.elf')).read_bytes()
            deployed = out / ('boot-' + name)
            launch = ram_launch.prepare(out / 'build/ram-boot.elf', guest, out / 'build/user1.elf',
                                        out / 'disk.raw', deployed, sha(guest))
            record['deployments'][name] = native_probe.run(deployed, launch, args.seconds)
            serial = (deployed / 'serial.log').read_text()
            assert 'suba native V9: handoff accepted' in serial
            assert ('suba L2: Sv39 active' if name == 's0' else 'suba K2: Sv39 active') in serial
            after = Disk(deployed / 'disk.raw', out / 'abi/contract.vt')
            assert after.read('/work/' + name + '.elf') == guest.read_bytes() == (deployed / 'kernel.elf').read_bytes()
            (deployed / 'hello.elf').write_bytes(after.read('/work/hello.elf'))
            assert sha(deployed / 'boot.elf') == record['fixed_boot']['sha256']
        assert (out / 'boot-vt/hello.elf').read_bytes() == (out / 'boot-s0/hello.elf').read_bytes()
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K9 native kernel and S0 builds, byte transport, new-kernel app builds passed')


if __name__ == '__main__':
    main()
