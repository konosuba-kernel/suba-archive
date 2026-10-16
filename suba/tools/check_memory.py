#!/usr/bin/env python3
"""Exercise the actual physical-page owner under Linux; QEMU kernel integration is separate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def segments(path):
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x02\x01':
        raise RuntimeError('expected little-endian ELF64')
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    result = []
    for index in range(count):
        kind, flags, _, address, _, filesz, memsz, align = struct.unpack_from(
            '<IIQQQQQQ', data, offset + index * size)
        if kind == 1:
            result.append(dict(flags=flags, address=address, file_bytes=filesz,
                               memory_bytes=memsz, bss_bytes=memsz-filesz, alignment=align))
    return result


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('test-copy mutation anchor is no longer unique')
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = [ROOT/'kernel/memory.vt', ROOT/'abi/contract.vt',
               *sorted((ROOT/'tests/memory').glob('*.vt')), Path(__file__).resolve()]
    record = dict(compiler=str(compiler), compiler_sha256=digest(compiler),
                  inputs={str(p.relative_to(ROOT)): digest(p) for p in sources},
                  scope='same production allocator, Linux identity-addressed ordinary RAM; '
                        'not full RAM discovery, user isolation or a kernel execution proof',
                  cases=[], passed=False)

    def run(command, cwd):
        result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=120)
        return dict(command=command, returncode=result.returncode,
                    stdout=result.stdout.decode(errors='replace'),
                    stderr=result.stderr.decode(errors='replace'))

    def case(name, probe, expected=0, mutation=None, abi_mutation=None, memory=True):
        folder = out/name
        folder.mkdir()
        shutil.copyfile(ROOT/'abi/contract.vt', folder/'contract.vt')
        shutil.copyfile(ROOT/'tests/memory/support.vt', folder/'support.vt')
        text = (ROOT/'kernel/memory.vt').read_text()
        if mutation:
            text = replace_once(text, *mutation)
        (folder/'memory.vt').write_text(text)
        if abi_mutation:
            text = replace_once((folder/'contract.vt').read_text(), *abi_mutation)
            (folder/'contract.vt').write_text(text)
        if isinstance(probe, Path):
            shutil.copyfile(probe, folder/'probe.vt')
        else:
            (folder/'probe.vt').write_text(probe)
        manifest = ('format 1\nprofile linux-user\nentry test::memory::run\n'
                    'source contract.vt\n')
        if memory:
            manifest += 'source memory.vt\n'
        if isinstance(probe, Path):
            manifest += 'source support.vt\n'
        manifest += 'source probe.vt\noutput probe.elf\n'
        (folder/'probe.build').write_text(manifest)
        evidence = dict(name=name, test_copy_mutation=mutation, abi_test_copy_mutation=abi_mutation,
                        expected_exit=expected, commands=[], passed=False,
                        inputs={p.name: digest(p) for p in folder.iterdir() if p.is_file()})
        record['cases'].append(evidence)
        build = run(['qemu-riscv64', '-s', '1048576', str(compiler), 'build', 'probe.build'], folder)
        evidence['commands'].append(build)
        if build['returncode'] != 0:
            raise RuntimeError(f'{name}: compilation failed: {build["stderr"]}')
        execution = run(['qemu-riscv64', '-s', '1048576', str(folder/'probe.elf')], folder)
        evidence['commands'].append(execution)
        if execution['returncode'] != expected:
            raise RuntimeError(f'{name}: expected {expected}, got {execution["returncode"]}')
        evidence['elf_sha256'] = digest(folder/'probe.elf')
        evidence['segments'] = segments(folder/'probe.elf')
        evidence['compiler_metrics'] = dict(re.findall(r'([a-z_]+)=([0-9]+)',
                                                       build['stdout'] + build['stderr']))
        evidence['passed'] = True
        print(f'{name}: passed', flush=True)
        return evidence

    try:
        tests = ROOT/'tests/memory'
        case('initialize', tests/'initialize.vt')
        case('lifecycle', tests/'lifecycle.vt')
        case('retirement-test-copy', tests/'retirement.vt', mutation=(
            'const GENERATION_MAX: u32 = 0xffffffff;', 'const GENERATION_MAX: u32 = 2;'))
        case('capacity-test-copy', tests/'initialize.vt', abi_mutation=(
            'pub const RAM_BYTES: usize = 0x20000000;', 'pub const RAM_BYTES: usize = 12288;'))
        case('missing-clear-negative', tests/'lifecycle.vt', expected=24,
             mutation=('        clear_page(index);', '        // TEST COPY: omit page clearing.'))
        case('missing-generation-negative', tests/'lifecycle.vt', expected=34,
             mutation=('        SLOTS[index].generation = SLOTS[index].generation + 1_u32;',
                       '        SLOTS[index].generation = 1_u32; // TEST COPY: stale identity reuse.'))
        case('regions-invalid', tests/'regions_invalid.vt')
        case('regions-high', tests/'regions_high.vt')
        case('regions-capacity', tests/'regions_capacity.vt')
        case('managed-bound-negative', tests/'regions_high.vt', expected=20,
             mutation=('frame.index as usize >= SPAN_PAGES', 'frame.index as usize >= COUNT'))
        case('cost-allocator', 'module test::memory;\nimport kernel::memory;\n'
             'pub fn run() -> u32 { return 0; }\n')
        case('cost-empty', 'module test::memory;\npub fn run() -> u32 { return 0; }\n', memory=False)
        record['passed'] = True
    finally:
        (out/'verification.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(dict(passed=True, cases=len(record['cases']), record=str(out/'verification.json'))))


if __name__ == '__main__':
    main()
