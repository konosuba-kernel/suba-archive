#!/usr/bin/env python3
"""Read a stopped suba disk for test evidence; never mount or modify the image.

The guest must have completed sync and stopped before using this observer.
"""
import argparse
from pathlib import Path
import struct
from mkfs import constants


class Disk:
    def __init__(self, path, contract):
        self.c = constants(contract)
        self.data = path.read_bytes()[self.c['FS_OFFSET']:]
        self.nodes = {}
        c = self.c
        for index in range(c['FS_NODE_COUNT']):
            offset = c['FS_NODES_START'] * c['BLOCK_BYTES'] + index * c['FS_NODE_BYTES']
            kind, flags, generation, parent, length, size, first, last = struct.unpack_from('<IIQIIQII', self.data, offset)
            if not kind:
                continue
            assert length <= c['NODE_NAME_MAX'] and kind in (c['NODE_FILE'], c['NODE_DIRECTORY'])
            name = self.data[offset + c['NODE_NAME']:offset + c['NODE_NAME'] + length].decode('utf-8')
            self.nodes[index] = dict(kind=kind, flags=flags, generation=generation,
                                     parent=parent, name=name, size=size, first=first, last=last)
        detached = constants(contract.parent.parent / 'kernel/fs/codec.vt')['DETACHED']
        # Detached old readers may remain in durable metadata until the bounded
        # reaper runs. They are not visible directory entries.
        self.paths = {self.path(index): index for index, node in self.nodes.items()
                      if not node['flags'] & detached}

    def path(self, index):
        components = []
        seen = set()
        while index:
            assert index not in seen and len(seen) < 16
            seen.add(index)
            node = self.nodes[index]
            components.append(node['name'])
            index = node['parent']
        return '/' + '/'.join(reversed(components))

    def read(self, path):
        c = self.c
        node = self.nodes[self.paths[path]]
        assert node['kind'] == c['NODE_FILE'] and node['size'] <= c['FS_FILE_BYTES_MAX']
        data = bytearray()
        block = node['first']
        seen = set()
        while len(data) < node['size']:
            assert c['FS_DATA_START'] <= block < c['FS_BLOCKS'] and block not in seen
            seen.add(block)
            offset = block * c['BLOCK_BYTES']
            data += self.data[offset:offset + c['BLOCK_BYTES']]
            block = struct.unpack_from('<I', self.data, c['FS_FAT_START'] * c['BLOCK_BYTES'] + block * 4)[0]
        assert not seen or block == c['FAT_END']
        return bytes(data[:node['size']])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disk', type=Path)
    parser.add_argument('path')
    parser.add_argument('--contract', type=Path, default=Path(__file__).resolve().parents[1] / 'abi/contract.vt')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = Disk(args.disk, args.contract).read(args.path)
    if args.output:
        with args.output.open('xb') as target:
            target.write(data)
    else:
        __import__('sys').stdout.buffer.write(data)


if __name__ == '__main__':
    main()
