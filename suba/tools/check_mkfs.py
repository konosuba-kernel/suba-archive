#!/usr/bin/env python3
"""Verify initial disk boundaries and decode its bytes independently of mkfs.

This checks the host formatter only. Real guest mount, mutation, and persistence
belong to check_k4; a host decoder cannot replace those observations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from mkfs import format_disk

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'abi/contract.vt'


def tree(path):
    for name in ('sys', 'work', 'jobs'):
        (path / name).mkdir(parents=True)
    return path


def decode(disk, source):
    # Literal wire values are an independent oracle for the documented v1 disk.
    assert disk.stat().st_size == 268435456
    with disk.open('rb') as stream:
        remaining = 68157440
        while remaining:
            block = stream.read(min(1048576, remaining))
            assert block and not any(block), 'reserved deployment area changed'
            remaining -= len(block)
        metadata = stream.read(193 * 4096)
        header = bytearray(metadata[:4096])
        assert struct.unpack_from('<Q9I', header) == (
            0x31534641425553, 1, 4096, 48896, 1, 64, 65, 4096, 193, 0)
        crc, = struct.unpack_from('<I', header, 44)
        struct.pack_into('<I', header, 44, 0)
        assert zlib.crc32(header) == crc
        assert not any(header[48:]), 'initial boot identity/reserved bytes'
        fat = struct.unpack_from('<65536I', metadata, 4096)
        assert all(item == 0xfffffffe for item in fat[:193])
        assert all(item == 0xfffffffe for item in fat[48896:])
        paths = {0: source}
        visited = set()
        nodes = files = 0
        for index in range(4096):
            record = metadata[65 * 4096 + index * 128:65 * 4096 + (index + 1) * 128]
            kind, flags, generation, parent, length, size, first, last = struct.unpack_from('<IIQIIQII', record)
            if kind == 0:
                assert not any(record)
                continue
            nodes += 1
            assert kind in (1, 2) and flags == 0 and generation == 1
            assert not any(record[40 + length:])
            if index == 0:
                assert (kind, parent, length, size, first, last) == (2, 0, 0, 0, 0, 0)
                continue
            assert parent < index and parent in paths and 1 <= length <= 63
            name = record[40:40 + length].decode('utf-8')
            assert name not in ('.', '..') and '/' not in name and '\0' not in name
            current = paths[parent] / name
            paths[index] = current
            if kind == 2:
                assert current.is_dir() and (size, first, last) == (0, 0, 0)
                continue
            files += 1
            assert current.is_file() and current.stat().st_size == size <= 16777216
            if size == 0:
                assert first == last == 0
                continue
            block = first
            remaining = size
            with current.open('rb') as original:
                while remaining:
                    assert 193 <= block < 48896 and block not in visited
                    visited.add(block)
                    stream.seek(68157440 + block * 4096)
                    data = stream.read(4096)
                    used = min(remaining, 4096)
                    assert data[:used] == original.read(used)
                    assert not any(data[used:]), 'nonzero file padding'
                    remaining -= used
                    if not remaining:
                        assert block == last and fat[block] == 0xffffffff
                    else:
                        block = fat[block]
        assert nodes == 1 + sum(1 for _ in source.rglob('*'))
        assert all(fat[index] == 0 for index in range(193, 48896) if index not in visited)
    return dict(nodes=nodes, files=files, data_blocks=len(visited),
                metadata_sha256=hashlib.sha256(metadata).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = dict(passed=False, scope='host formatter; no guest persistence claim', cases=[],
                  inputs={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in (Path(__file__).resolve(), ROOT / 'tools/mkfs.py', CONTRACT)})

    def accept(name, source):
        image = out / (name + '.raw')
        report = format_disk(source, image, CONTRACT)
        actual = decode(image, source)
        assert report['nodes'] == actual['nodes']
        assert report['allocated_data_blocks'] == actual['data_blocks']
        assert report['metadata_sha256'] == actual['metadata_sha256']
        record['cases'].append(dict(name=name, accepted=True, decoded=actual))
        return image

    def reject(name, source):
        image = out / (name + '.raw')
        try:
            format_disk(source, image, CONTRACT)
        except ValueError as error:
            assert not image.exists(), 'invalid input left output behind'
            record['cases'].append(dict(name=name, accepted=False, error=str(error)))
        else:
            raise AssertionError('invalid input accepted: ' + name)

    try:
        source = tree(out / 'basic')
        (source / 'work/中文.vt').write_bytes('module sample; // 中文\n'.encode())
        (source / 'work/cross.bin').write_bytes(bytes(range(256)) * 17)
        (source / 'sys/empty').write_bytes(b'')
        image = accept('basic', source)
        try:
            format_disk(source, image, CONTRACT)
        except FileExistsError:
            decode(image, source)
            record['cases'].append(dict(name='existing-output', accepted=False, preserved=True))
        else:
            raise AssertionError('existing output overwritten')
        for name, create in (
            ('symlink', lambda path: path.symlink_to('cross.bin')),
            ('a' * 64, lambda path: path.write_bytes(b'')),
        ):
            path = source / 'work' / name
            create(path)
            reject('reject-' + name, source)
            path.unlink()
        (source / 'jobs/unexpected').write_bytes(b'')
        reject('nonempty-jobs', source)
        (source / 'jobs/unexpected').unlink()
        (source / 'sys').rename(source / 'system')
        reject('missing-sys', source)
        (source / 'system').rename(source / 'sys')
        (source / 'work' / ('中' * 21)).write_bytes(b'')
        accept('name-63-bytes', source)
        (source / 'work' / ('中' * 22)).write_bytes(b'')
        reject('name-66-bytes', source)

        deep = tree(out / 'depth')
        directory = deep / 'work'
        for _ in range(15):
            directory /= 'd'
            directory.mkdir()
        accept('depth-16', deep)
        (directory / 'd').mkdir()
        reject('depth-17', deep)

        full_nodes = tree(out / 'nodes')
        for index in range(4092):
            (full_nodes / 'work' / str(index)).write_bytes(b'')
        accept('nodes-4096', full_nodes)
        (full_nodes / 'work/overflow').write_bytes(b'')
        reject('nodes-4097', full_nodes)

        full_data = tree(out / 'data')
        remaining = (48896 - 193) * 4096
        index = 0
        while remaining:
            size = min(16777216, remaining)
            with (full_data / 'work' / str(index)).open('wb') as stream:
                stream.truncate(size)
            remaining -= size
            index += 1
        accept('data-full', full_data)
        (full_data / 'work/overflow').write_bytes(b'x')
        reject('data-overflow', full_data)
        with (full_data / 'work/0').open('ab') as stream:
            stream.write(b'x')
        reject('file-over-16MiB', full_data)
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    print(f"mkfs: {len(record['cases'])} boundary and byte-decoding cases passed")


if __name__ == '__main__':
    main()
