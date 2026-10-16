#!/usr/bin/env python3
"""Build a bootable suba working environment from frozen source inputs.

QEMU uses fixed RAM boot and a real virtio disk. Initial compiler/application ELF
files are host-built seeds; subsequent builds use /sys/compiler.elf inside suba.
"""
import argparse
import json
from pathlib import Path
import shutil

import build_users
import kernel_probe
import fixed_boot
import native_manifests
import ram_launch
from mkfs import format_disk
from check_k2 import sha

ROOT = Path(__file__).resolve().parents[1]


def manifest_program(path):
    lines = path.read_text().splitlines()
    return dict(entry=next(line[6:] for line in lines if line.startswith('entry ')),
                sources=[line[7:] for line in lines if line.startswith('source ')],
                assembly=[line[9:] for line in lines if line.startswith('assembly ')])


def build(compiler, out, record, reuse=None, kernel_from=None):
    record['compiler_sha256'] = sha(compiler)
    record['source_inputs'] = kernel_probe.snapshot(out)
    # Freeze all user sources before any long compilation starts.
    descriptions = {name: manifest_program(ROOT / path) for name, path in [
        ('desktop', 'user/desktop/desktop.build'), ('edit', 'user/edit/edit.build'), ('build', 'user/build/build.build')]}
    descriptions['compiler'] = dict(entry='bootstrap::main::run',
                                   sources=build_users.compiler_sources(), assembly=['user/libsuba/syscall.s0'])
    for program in descriptions.values():
        for name in program['sources'] + program['assembly']:
            target = out / name
            data = build_users.source_path(name).read_bytes()
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError('conflicting frozen input ' + name)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    # Only trusted desktop is a boot-time RAM image; all ordinary apps load from FS.
    run = kernel_probe.build(compiler, out, [descriptions['desktop']], record, kernel_from or reuse)
    products = {}
    for name in ('edit', 'build', 'compiler'):
        program = descriptions[name]
        products[name] = build_users.build(compiler, out, name, program['entry'],
                                          program['sources'], record, assembly=program['assembly'], reuse=reuse)
    tree = out / 'initial'
    for name in ('sys', 'work', 'jobs'):
        (tree / name).mkdir(parents=True)
    for name, path in products.items():
        shutil.copyfile(path, tree / 'sys' / (name + '.elf'))
    shutil.copyfile(ROOT / 'assets/unifont/suba-bmp.fnt', tree / 'sys/suba-bmp.fnt')
    # Keep font attribution and original data with the shipped bitmap.
    shutil.copytree(ROOT / 'assets/unifont', tree / 'sys/font-source')
    (tree / 'work/hello.vt').write_text('// 你好，suba。\nmodule demo;\npub fn main() -> u32 {\n    return 41;\n}\n')
    (tree / 'work/notes.txt').write_text('你好，suba。\n这是独立文本窗口。\n编译期间仍可编辑和保存。\n')
    (tree / 'work/program.build').write_text('format 1\nprofile suba-user\nentry demo::main\n'
        'source hello.vt\nassembly syscall.s0\noutput hello.elf\n')
    shutil.copyfile(out / 'user/libsuba/syscall.s0', tree / 'work/syscall.s0')
    # Source inputs are ordinary editable files. Generated ELFs remain distinct.
    for name in sorted(record['compiled_inputs']):
        if name.endswith(('.vt', '.s0', '.build')) and not name.startswith(('tests/', 'test_')):
            target = tree / 'work/system' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out / name, target)
    for name, item in record.get('programs', {}).items():
        for relative in item['inputs']:
            if relative.endswith(('.vt', '.s0', '.build')):
                target = tree / 'work/system' / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(out / relative, target)
    native_manifests.install(out, tree / 'work')
    boot = fixed_boot.build(ROOT, compiler, out, record, reuse)
    record['initial_disk'] = format_disk(tree, out / 'disk.raw', out / 'abi/contract.vt')
    run = ram_launch.prepare(boot, out / 'build/kernel.elf', out / 'build/user0.elf',
                             out / 'disk.raw', out / 'deployment', record['kernel']['sha256'])
    record['deployment'] = str(out / 'deployment')
    record['persistent_disk'] = str(out / 'deployment/disk.raw')
    run.remove('-nographic')
    run += ['-serial', 'stdio', '-monitor', 'none', '-display', 'gtk']
    record['run_command'] = run
    (out / 'run.json').write_text(json.dumps(run, indent=2) + '\n')
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--reuse', type=Path, help='reuse only byte-identical compiler/kernel/user inputs')
    parser.add_argument('--kernel-from', type=Path, help='reuse an independently frozen matching kernel')
    args = parser.parse_args()
    out = args.out.resolve()
    record = {'built': False, 'guest_verified': False}
    try:
        build(args.compiler.resolve(), out, record, args.reuse.resolve() if args.reuse else None,
              args.kernel_from.resolve() if args.kernel_from else None)
        record['built'] = True
    finally:
        if out.exists():
            (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'built': True, 'out': str(out), 'run': str(out / 'run.json')}))


if __name__ == '__main__':
    main()
