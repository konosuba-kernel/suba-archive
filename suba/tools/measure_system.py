#!/usr/bin/env python3
"""Report physical source lines and ELF load costs without counting frozen history."""
import argparse
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {'.vt', '.s0'}
SUPPORT = SOURCE | {'.py', '.rs', '.sh'}


def count(root, suffixes):
    files = []
    if root.exists():
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix in suffixes and '__pycache__' not in path.parts:
                data = path.read_bytes()
                lines = data.decode('utf-8').splitlines()
                files.append({'path': str(path.relative_to(ROOT.parent)), 'lines': len(lines),
                              'nonblank_lines': sum(bool(line.strip()) for line in lines), 'bytes': len(data)})
    return {'files': len(files), 'lines': sum(item['lines'] for item in files),
            'nonblank_lines': sum(item['nonblank_lines'] for item in files),
            'bytes': sum(item['bytes'] for item in files), 'detail': files}


def elf(path):
    data = path.read_bytes()
    assert data[:7] == b'\x7fELF\x02\x01\x01'
    table = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    segments = []
    for i in range(count):
        kind, flags, offset, address, physical, file_bytes, memory_bytes, alignment = struct.unpack_from('<IIQQQQQQ', data, table + i * size)
        if kind == 1:
            segments.append({'address': address, 'flags': flags, 'file_bytes': file_bytes,
                             'memory_bytes': memory_bytes, 'zero_bytes': memory_bytes - file_bytes,
                             'mapped_pages': (memory_bytes + 4095) // 4096})
    return {'file_bytes': len(data), 'load_memory_bytes': sum(s['memory_bytes'] for s in segments),
            'load_pages': sum(s['mapped_pages'] for s in segments), 'segments': segments,
            'note': 'PT_LOAD only; runtime page tables, stack, requests and surfaces are additional'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, help='optional built system snapshot')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    groups = {}
    for name, relative in [('compiler', '../biomiya/compiler'), ('kernel', 'kernel'), ('abi', 'abi'),
                           ('platform', 'platform'), ('boot', 'boot'), ('user', 'user')]:
        groups[name] = count((ROOT / relative).resolve(), SOURCE)
    support = {}
    for name, relative in [('suba_tests', 'tests'), ('suba_tools', 'tools'),
                           ('compiler_tests', '../biomiya/tests'), ('compiler_tools', '../biomiya/tools')]:
        support[name] = count((ROOT / relative).resolve(), SUPPORT)
    record = {'method': 'Physical lines including comments and blank lines. Current source directories only; no build outputs, bootstrap, legacy, docs or font binary data.',
              'implementation': groups, 'implementation_lines': sum(g['lines'] for g in groups.values()),
              'tests_tools': support, 'tests_tools_lines': sum(g['lines'] for g in support.values()), 'elf': {}}
    record['assets'] = [{'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size}
                        for path in sorted((ROOT / 'assets').rglob('*')) if path.is_file()]
    record['asset_bytes'] = sum(item['bytes'] for item in record['assets'])
    if args.system:
        for path in sorted((args.system / 'build').glob('*.elf')):
            record['elf'][path.name] = elf(path)
    args.output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'implementation_lines': record['implementation_lines'],
                      'tests_tools_lines': record['tests_tools_lines'], 'groups': {k: v['lines'] for k, v in groups.items()}}))


if __name__ == '__main__':
    main()
