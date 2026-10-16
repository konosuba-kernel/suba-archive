#!/usr/bin/env python3
"""Execute the production snapshot planner and SHA-256 on RV64 with byte oracles."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import build_users


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    compiler, out = args.compiler.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = {'passed': False, 'cases': [], 'compiler_sha256': build_users.digest(compiler)}
    common = ['user/build/manifest.vt', 'biomiya/compiler/runtime/bytes.vt', 'user/text/utf8.vt']
    transport = ['tests/k6/transport.vt']
    def build(name, entry, sources):
        return build_users.build(compiler, out, name, entry, sources, record,
                                 profile='linux-user', assembly=['tools/fontpack/linux.s0'])
    def run(name, exe, data, expected, code=0):
        result = subprocess.run(['qemu-riscv64', '-s', '1048576', str(exe)], input=data,
                                capture_output=True, timeout=30)
        item = {'name': name, 'input_sha256': hashlib.sha256(data).hexdigest(),
                'actual_exit': result.returncode, 'expected_exit': code,
                'output_sha256': hashlib.sha256(result.stdout).hexdigest(),
                'passed': result.returncode == code and result.stdout == expected and not result.stderr}
        record['cases'].append(item)
        if not item['passed']:
            (out / (name + '.input')).write_bytes(data)
            (out / (name + '.actual')).write_bytes(result.stdout)
            (out / (name + '.expected')).write_bytes(expected)
            raise AssertionError(item)
    try:
        planner = build('planner', 'test::manifest::run', common + transport + ['tests/k7/manifest_probe.vt'])
        context = build('context', 'test::context::run', common + ['tests/k7/manifest_context.vt'])
        sha = build('sha', 'test::sha::run', transport + ['user/build/sha256.vt', 'tests/k7/sha_probe.vt'])
        run('context-nine-boundaries', context, b'', b'')
        def check(name, sources, assemblies=(), output='result.elf', accepted=True, profile='suba-user'):
            source = f'format 1\nprofile {profile}\nentry demo::main\n'
            source += ''.join('source ' + p + '\n' for p in sources)
            source += ''.join('assembly ' + p + '\n' for p in assemblies)
            source += 'output ' + output + '\n'
            expected = b''
            if accepted:
                rewritten = f'format 1\nprofile {profile}\nentry demo::main\n'
                rewritten += ''.join('source src/' + p + '\n' for p in sources)
                rewritten += ''.join('assembly src/' + p + '\n' for p in assemblies)
                rewritten += 'output out/result.elf\n'
                encoded = rewritten.encode()
                expected = struct.pack('<II', len(sources) + len(assemblies), len(encoded)) + encoded
                for asm, paths in enumerate((sources, assemblies)):
                    for path in paths:
                        data = path.encode()
                        expected += struct.pack('<II', asm, len(data)) + data
                expected += output.encode()
            run(name, planner, source.encode(), expected, 0 if accepted else 1)
        check('normal', ['hello.vt'], ['syscall.s0'])
        check('chinese-path', ['源/你好.vt'])
        check('kernel-target', ['kernel.vt'], profile='suba-kernel')
        check('linux-target-rejected', ['main.vt'], profile='linux-user', accepted=False)
        for count in (63, 64):
            check('component-' + str(count), ['a' * count], accepted=count == 63)
        for count in (13, 14):
            check('depth-' + str(count), ['/'.join(['a'] * count)], accepted=count == 13)
        for count in (92, 93):
            check('path-bytes-' + str(count), ['a' * 45 + '/' + 'b' * (count - 46)], accepted=count == 92)
        for count in (64, 65):
            check('sources-' + str(count), [f'f{i}.vt' for i in range(count)], accepted=count == 64)
        for count in (8, 9):
            check('assembly-' + str(count), ['main.vt'], [f'f{i}.s0' for i in range(count)], accepted=count == 8)
        for i, paths in enumerate((['a', 'a'], ['a', 'a/b'], ['a/b', 'a'], ['../a'], ['/a'],
                                   ['program.build'], ['program.build/child'], ['.suba-inputs.txt'], ['a//b'])):
            check('invalid-source-' + str(i), paths, accepted=False)
        for i, output in enumerate(('a', 'a/b', '.suba-records/x', 'dir/.suba-save-x', '../out', '/work/out')):
            check('invalid-output-' + str(i), ['a'], output=output, accepted=False)
        for size in (0, 1, 55, 56, 63, 64, 65, 127, 128, 129, 4096, 65535, 1048575):
            data = bytes((i * 37 + 11) % 256 for i in range(size))
            for chunk in (1, 64, 255):
                run(f'sha-{size}-{chunk}', sha, bytes([chunk - 1]) + data, hashlib.sha256(data).digest())
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K7 planner/hash checks passed:', len(record['cases']))


if __name__ == '__main__':
    main()
