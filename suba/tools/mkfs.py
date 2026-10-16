#!/usr/bin/env python3
"""Construct an initial suba disk from a directory; never serve guest file calls.

The boot slots remain zero (RAM deployment). The source must have sys/work/jobs
as directories; the kernel alone creates runtime Job subdirectories.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib


def constants(contract: Path) -> dict[str, int]:
    result = {}
    for name, value in re.findall(r'^pub const ([A-Z_0-9]+): (?:usize|u32) = (0x[0-9a-f]+|[0-9]+);$', contract.read_text(), re.M):
        result[name] = int(value, 0)
    return result


def format_disk(source: Path, output: Path, contract: Path) -> dict:
    c = constants(contract)
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError('source must be a directory')
    for name in ('sys', 'work', 'jobs'):
        if (source / name).is_symlink() or not (source / name).is_dir():
            raise ValueError(f'{name} must be a real directory')
    if any((source / 'jobs').iterdir()):
        raise ValueError('initial /jobs must be empty')
    block_bytes = c['BLOCK_BYTES']
    metadata = bytearray(c['FS_DATA_START'] * block_bytes)
    fat = [c['FAT_RESERVED']] * (c['FS_FAT_BLOCKS'] * block_bytes // 4)
    for index in range(c['FS_DATA_START'], c['FS_BLOCKS']):
        fat[index] = c['FAT_FREE']
    entries = [(source, 0, b'', 0)]
    # Parent indices refer to this stable breadth-first sequence.
    at = 0
    while at < len(entries):
        path, parent, name, depth = entries[at]
        if path.is_symlink():
            raise ValueError(f'symlink is unsupported: {path}')
        if path.is_dir():
            for child in sorted(path.iterdir(), key=lambda p: p.name.encode('utf-8')):
                encoded = child.name.encode('utf-8')
                if not 1 <= len(encoded) <= c['NODE_NAME_MAX'] or encoded in (b'.', b'..') or b'\0' in encoded:
                    raise ValueError(f'invalid component: {child}')
                if depth + 1 > 16:
                    raise ValueError(f'path depth exceeds 16: {child}')
                if len(entries) == c['FS_NODE_COUNT']:
                    raise ValueError('node table full')
                entries.append((child, at, encoded, depth + 1))
        elif not path.is_file():
            raise ValueError(f'only regular files/directories supported: {path}')
        at += 1
    # Finish all capacity/input validation before creating the output.
    payloads = []
    next_block = c['FS_DATA_START']
    files = []
    for index, (path, parent, name, depth) in enumerate(entries):
        first = last = size = 0
        kind = c['NODE_DIRECTORY']
        if path.is_file():
            kind = c['NODE_FILE']
            if path.stat().st_size > c['FS_FILE_BYTES_MAX']:
                raise ValueError(f'file exceeds 16 MiB: {path}')
            data = path.read_bytes()
            size = len(data)
            if size > c['FS_FILE_BYTES_MAX']:
                raise ValueError(f'file grew past 16 MiB: {path}')
            count = (size + block_bytes - 1) // block_bytes
            if count > c['FS_BLOCKS'] - next_block:
                raise ValueError('data region full')
            if count:
                first, last = next_block, next_block + count - 1
                for item in range(first, last):
                    fat[item] = item + 1
                fat[last] = c['FAT_END']
                payloads.append((first * block_bytes, data))
                next_block += count
            files.append({'path': '/' + path.relative_to(source).as_posix(), 'bytes': size,
                          'sha256': hashlib.sha256(data).hexdigest()})
        record = c['FS_NODES_START'] * block_bytes + index * c['FS_NODE_BYTES']
        struct.pack_into('<IIQIIQII', metadata, record, kind, 0, 1, parent, len(name), size, first, last)
        metadata[record + c['NODE_NAME']:record + c['NODE_NAME'] + len(name)] = name
    struct.pack_into('<' + 'I' * len(fat), metadata, c['FS_FAT_START'] * block_bytes, *fat)
    struct.pack_into('<Q10I', metadata, 0, c['FS_MAGIC_VALUE'], c['VERSION'], block_bytes,
                     c['FS_BLOCKS'], c['FS_FAT_START'], c['FS_FAT_BLOCKS'], c['FS_NODES_START'],
                     c['FS_NODE_COUNT'], c['FS_DATA_START'], 0, 0)
    struct.pack_into('<I', metadata, c['FS_SUPER_CRC32'], zlib.crc32(metadata[:block_bytes]))
    with output.open('xb') as stream:
        stream.truncate(c['DISK_BYTES'])
        stream.seek(c['FS_OFFSET'])
        stream.write(metadata)
        for offset, data in payloads:
            stream.seek(c['FS_OFFSET'] + offset)
            stream.write(data)
    return {'format': 1, 'nodes': len(entries), 'allocated_data_blocks': next_block - c['FS_DATA_START'],
            'metadata_sha256': hashlib.sha256(metadata).hexdigest(), 'files': files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = format_disk(args.source, args.output, args.contract)
    if args.report:
        with args.report.open('x') as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
    print(f"created {args.output}: {report['nodes']} nodes, {report['allocated_data_blocks']} data blocks")


if __name__ == '__main__':
    main()
