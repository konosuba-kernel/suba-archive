#!/usr/bin/env python3
"""Freeze and compile current user programs, including the same biomiya core.

Only constructs startup inputs. Guest compilation uses its own disk and syscalls.
The output directory is a snapshot; existing files must be byte-identical.
"""
from pathlib import Path
import hashlib
import subprocess
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
BIOMIYA = ROOT.parent / 'biomiya'
COMMON = ['abi/contract.vt', 'abi/syscalls.vt', 'abi/files.vt', 'abi/argument_wire.vt',
          'user/libsuba/syscall.vt', 'user/libsuba/services.vt',
          'user/libsuba/arguments.vt', 'user/libsuba/argument_builder.vt', 'user/libsuba/files.vt']


def compiler_sources():
    names = [line.split(' ', 1)[1] for line in (BIOMIYA / 'compiler/compiler.build').read_text().splitlines()
             if line.startswith('source ')]
    names = [name for name in names if name not in ('compiler/runtime/linux.vt', 'compiler/runtime/host_linux.vt')]
    return ['biomiya/' + name for name in names + ['compiler/runtime/host_suba.vt']] + COMMON


def source_path(name):
    if name.startswith('biomiya/'):
        return BIOMIYA / name.removeprefix('biomiya/')
    return ROOT / name


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(compiler, out, name, entry, sources, record, profile='suba-user', assembly=None, reuse=None):
    if assembly is None:
        assembly = ['user/libsuba/syscall.s0']
    sources = list(dict.fromkeys(sources))
    for path in sources + assembly:
        target = out / path
        data = source_path(path).read_bytes()
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError('snapshot input changed: ' + path)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    (out / 'build').mkdir(exist_ok=True)
    lines = ['format 1', 'profile ' + profile, 'entry ' + entry]
    lines += ['source ' + path for path in sources]
    lines += ['assembly ' + path for path in assembly]
    lines += ['output build/' + name + '.elf']
    manifest = name + '.build'
    (out / manifest).write_text('\n'.join(lines) + '\n')
    inputs = {path: digest(out / path) for path in sources + assembly + [manifest]}
    if reuse is not None:
        previous = json.loads((reuse / 'verification.json').read_text())
        item = previous.get('programs', {}).get(name)
        if previous.get('compiler_sha256') == digest(compiler) and item and item['inputs'] == inputs:
            source = reuse / 'build' / (name + '.elf')
            if digest(source) != item['sha256']:
                raise ValueError('cached user ELF changed: ' + name)
            target = out / 'build' / (name + '.elf')
            shutil.copyfile(source, target)
            record.setdefault('programs', {})[name] = dict(item, reused_from=str(reuse))
            return target
    command = ['qemu-riscv64', '-s', '1048576', str(compiler), 'build', manifest]
    result = subprocess.run(command, cwd=out, capture_output=True, timeout=600)
    (out / (name + '-compile.log')).write_bytes(result.stdout + result.stderr)
    item = dict(command=command, returncode=result.returncode,
                inputs=inputs)
    record.setdefault('programs', {})[name] = item
    if result.returncode:
        raise RuntimeError(result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace'))
    target = out / 'build' / (name + '.elf')
    item.update(sha256=digest(target), bytes=target.stat().st_size)
    return target
