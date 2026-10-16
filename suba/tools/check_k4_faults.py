#!/usr/bin/env python3
"""Boot real malformed disks and inject QEMU block errors into a frozen K4 run.

Consumes check_k4 filesystem's frozen build. No guest host-file service, no ELF
patching. Every case gets fresh storage; panic evidence is required, so a QEMU
startup error or host timeout alone can never pass.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import shutil
import subprocess
import zlib

from mkfs import format_disk
from kernel_probe import ROOT, build

FS_OFFSET = 68157440
BLOCK = 4096
NODE_OFFSET = 65 * BLOCK


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def change_disk(path, case):
    with path.open('r+b') as stream:
        stream.seek(FS_OFFSET)
        metadata = bytearray(stream.read(193 * BLOCK))
        if case == 'bad_crc':
            metadata[44] ^= 1
        elif case == 'bad_layout':
            struct.pack_into('<I', metadata, 16, 48895)
            struct.pack_into('<I', metadata, 44, 0)
            struct.pack_into('<I', metadata, 44, zlib.crc32(metadata[:BLOCK]))
        elif case == 'bad_utf8':
            # Initial tree is root/jobs/sys/work/work/中文.vt in BFS order.
            metadata[NODE_OFFSET + 4 * 128 + 40] = 0xff
        elif case == 'fat_cycle':
            struct.pack_into('<I', metadata, BLOCK + 193 * 4, 193)
        stream.seek(FS_OFFSET)
        stream.write(metadata)


def run_case(base_command, out, name, panic, injection=None, contract=None):
    case = out / name
    case.mkdir()
    tree = case / 'initial'
    for name_part in ('sys', 'work', 'jobs'):
        (tree / name_part).mkdir(parents=True)
    (tree / 'work/中文.vt').write_text('module hello; // 中文\n')
    disk = case / 'disk.raw'
    initial = format_disk(tree, disk, contract or ROOT / 'abi/contract.vt')
    change_disk(disk, name)
    backing = str(disk)
    if injection:
        event, relative_sector = injection
        config = case / 'blkdebug.conf'
        lines = ['[inject-error]', f'event = "{event}"', 'errno = "5"', 'once = "on"']
        if relative_sector is not None:
            lines.append(f'sector = "{FS_OFFSET // 512 + relative_sector}"')
        config.write_text('\n'.join(lines) + '\n')
        backing = f'blkdebug:{config}:{disk}'
    command = base_command.copy()
    drive_index = command.index('-drive') + 1
    command[drive_index] = (f'file={backing},if=none,format=raw,id=blk,cache=writeback,'
                            'rerror=report,werror=report')
    timed_out = False
    try:
        result = subprocess.run(command, capture_output=True, timeout=8 if panic else 90)
        log = result.stdout + result.stderr
        code = result.returncode
    except subprocess.TimeoutExpired as stopped:
        timed_out = True
        log = (stopped.stdout or b'') + (stopped.stderr or b'')
        code = None
    (case / 'boot.log').write_bytes(log)
    record = dict(command=command, initial=initial, exit=code, timed_out=timed_out,
                  log_sha256=digest(case / 'boot.log'), expected_panic=panic)
    if panic:
        record['passed'] = (f'suba kernel panic reason={panic}\n'.encode() in log
                            and b'suba K4: resource baseline\n' not in log
                            and b'suba K3: root exit 0\n' not in log)
        if panic in (71, 73):
            record['passed'] &= b'suba K4: mounted boot=1\n' in log
        else:
            record['passed'] &= b'suba K4: mounted boot=' not in log
    else:
        record['passed'] = (code == 0 and b'panic' not in log
                            and b'suba K3: root exit 0\n' in log
                            and b'suba K4: resource baseline\n' in log)
    (case / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-from', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--compiler', type=Path, help='also compile and run missing-completion timeout probe')
    args = parser.parse_args()
    source, out = args.kernel_from.resolve(), args.out.resolve()
    previous = json.loads((source / 'verification.json').read_text())
    assert previous['passed'] and previous['case'] == 'filesystem'
    assert previous['kernel']['sha256'] == digest(source / 'build/kernel.elf')
    for name, expected in previous['compiled_inputs'].items():
        assert digest(source / name) == expected, 'frozen source changed: ' + name
    artifacts = {str(path): digest(path) for path in (source / 'build').iterdir() if path.is_file()}
    out.mkdir(parents=True, exist_ok=False)
    cases = [('healthy', None, None)]
    cases += [(name, 70, None) for name in ('bad_crc', 'bad_layout', 'bad_utf8', 'fat_cycle')]
    cases += [('mount_read_eio', 70, ('read_aio', 8)),
              ('serial_write_eio', 70, ('write_aio', 0)),
              ('mount_flush_eio', 70, ('flush_to_disk', None)),
              ('data_write_eio', 71, ('write_aio', 194 * 8)),
              ('metadata_write_eio', 71, ('write_aio', 8)),
              ('data_read_eio', 71, ('read_aio', 194 * 8))]
    record = dict(source=str(source), source_report_sha256=digest(source / 'verification.json'),
                  kernel_sha256=digest(source / 'build/kernel.elf'), artifacts=artifacts, cases={}, passed=False)
    try:
        for name, panic, injection in cases:
            result = run_case(previous['run_command'], out, name, panic, injection, source / 'abi/contract.vt')
            record['cases'][name] = result
            print(name, 'PASS' if result['passed'] else 'FAIL', flush=True)
        if args.compiler:
            timeout_root = out / 'timeout-build'
            timeout_root.mkdir()
            (timeout_root / 'build').mkdir()
            for name in previous['compiled_inputs']:
                target = timeout_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target)
            # This boot source is an input of kernel_probe but not its generated manifest.
            for name in ('tests/k0/boot.vt', 'tests/k0/fw_cfg.vt'):
                target = timeout_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target)
            entry = timeout_root / 'kernel/entry.vt'
            code = entry.read_text()
            anchor = '        if !dispatch::boot(0)'
            assert code.count(anchor) == 1
            entry.write_text(code.replace(anchor, '        hub::test_hold_completion();\n' + anchor))
            hub = timeout_root / 'kernel/device/hub.vt'
            hub.write_text(hub.read_text() + """
// TEST ONLY: real requests complete in the device, but no completion IRQ reaches
// the driver. The unmodified block::state deadline must stop the filesystem.
pub unsafe fn test_hold_completion() -> () {
    unsafe { io::write32(devices::MMIO_OFFSET + devices::PLIC_ENABLE + 0x80_usize, 0); }
    return ();
}
""")
            manifest = (source / 'user0.build').read_text().splitlines()
            program = dict(entry=next(line[6:] for line in manifest if line.startswith('entry ')),
                           sources=[line[7:] for line in manifest if line.startswith('source ')],
                           assembly=[line[9:] for line in manifest if line.startswith('assembly ')])
            built = dict(compiler_sha256=digest(args.compiler.resolve()))
            command = build(args.compiler.resolve(), timeout_root, [program], built)
            command += ['-global', 'virtio-mmio.force-legacy=false', '-drive', 'replaced',
                        '-device', 'virtio-blk-device,drive=blk']
            (timeout_root / 'build-record.json').write_text(json.dumps(built, indent=2) + '\n')
            result = run_case(command, out, 'completion_timeout', 73,
                              contract=source / 'abi/contract.vt')
            record['cases']['completion_timeout'] = result
            record['timeout_build'] = built
            print('completion_timeout', 'PASS' if result['passed'] else 'FAIL', flush=True)
        record['passed'] = all(item['passed'] for item in record['cases'].values())
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    assert record['passed'], 'see per-case boot.log and result.json'


if __name__ == '__main__':
    main()
