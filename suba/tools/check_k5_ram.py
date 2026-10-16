#!/usr/bin/env python3
"""Native byte-oracle tests for clipped drawing and the production RAM copier."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from check_k5_devices import ROOT, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    compiler, out = args.compiler.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    names = ['tests/k5/draw_boundaries.vt', 'tests/k5/ram_copy.vt',
             'user/draw/pixels.vt', 'kernel/window_surface.vt']
    for name in names:
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    text = (out / 'kernel/window_surface.vt').read_text()
    begin = text.index('unsafe fn copy_ram(')
    end = text.index('// Caller supplies an exclusive', begin)
    # Exact private function, no algorithm transcription or production visibility change.
    (out / 'copy.vt').write_text('module kernel::window;\n' + text[begin:end])
    record = {'passed': False, 'compiler_sha256': sha(compiler),
              'inputs': {name: sha(out / name) for name in names}, 'runs': []}
    try:
        for kind, entry, sources in [
            ('draw', 'test::draw_boundaries::main', names[:1] + ['user/draw/pixels.vt']),
            ('copy', 'kernel::window::check_copy', ['tests/k5/ram_copy.vt', 'copy.vt'])]:
            manifest = ['format 1', 'profile linux-user', 'entry ' + entry]
            manifest += ['source ' + name for name in sources]
            manifest += ['output ' + kind + '.elf']
            (out / (kind + '.build')).write_text('\n'.join(manifest) + '\n')
            compiled = subprocess.run(['qemu-riscv64', '-s', '1048576', str(compiler), 'build', kind + '.build'],
                                      cwd=out, capture_output=True, timeout=120)
            (out / (kind + '-compile.log')).write_bytes(compiled.stdout + compiled.stderr)
            assert compiled.returncode == 0, compiled.stdout + compiled.stderr
            run = subprocess.run(['qemu-riscv64', str(out / (kind + '.elf'))], capture_output=True, timeout=60)
            (out / (kind + '-run.log')).write_bytes(run.stdout + run.stderr)
            assert run.returncode == 0, (kind, run.returncode)
            record['runs'].append({'kind': kind, 'elf_sha256': sha(out / (kind + '.elf')), 'exit': run.returncode})
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Drawing and RAM copy alignment/canary boundaries passed')


if __name__ == '__main__':
    main()
