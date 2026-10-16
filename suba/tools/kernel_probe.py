#!/usr/bin/env python3
"""Shared QEMU fixture construction: frozen kernel snapshot, RAM loader and U images.

Only creates startup inputs. Runtime files are always served by guest storage.
Callers explicitly edit the snapshot for test observations/fault injection before
building; this module never patches an ELF or changes generated machine code.
"""
from pathlib import Path
import shutil
import struct
from check_k2 import command, sha, DESCRIPTOR, KERNEL_SOURCE, IMAGE_SOURCE
from check_kernel_entry import image, FIRMWARE, require

ROOT = Path(__file__).resolve().parents[1]


def snapshot(out):
    out.mkdir(parents=True, exist_ok=False)
    manifest = ROOT / 'kernel/kernel.build'
    names = [line.split(' ', 1)[1] for line in manifest.read_text().splitlines()
             if line.startswith(('source ', 'assembly '))]
    names += ['kernel/kernel.build', 'tests/k0/boot.vt', 'tests/k0/fw_cfg.vt']
    for name in names:
        dst = out / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dst)
    (out / 'build').mkdir()
    return {name: sha(out / name) for name in names}


def build(compiler, out, programs, record, reuse_kernel=None):
    """programs is a list of {entry,sources,assembly}; each path is repo-relative."""
    # Freeze user sources at entry as well; a long kernel build must not read later
    # live edits into a nominally single test run.
    for program in programs:
        for name in program['sources'] + program['assembly']:
            dst = out / name
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, dst)
    def compile(manifest):
        # Full K5/K7 combinations exceed K2's small-fixture build time. This is
        # a host construction deadline, never a guest runtime acceptance limit.
        command(['qemu-riscv64', '-s', '1048576', str(compiler), 'build', manifest],
                out, record.setdefault('commands', []), timeout=600)
    if reuse_kernel is None:
        compile('kernel/kernel.build')
    else:
        import json
        previous = json.loads((reuse_kernel / 'verification.json').read_text())
        require(previous['compiler_sha256'] == sha(compiler), 'cached kernel compiler changed')
        manifest = out / 'kernel/kernel.build'
        names = ['kernel/kernel.build'] + [line.split(' ', 1)[1] for line in manifest.read_text().splitlines()
                 if line.startswith(('source ', 'assembly '))]
        for name in names:
            require(previous['compiled_inputs'][name] == sha(out / name), 'cached kernel input changed: ' + name)
        require(previous['kernel']['sha256'] == sha(reuse_kernel / 'build/kernel.elf'), 'cached kernel ELF changed')
        shutil.copyfile(reuse_kernel / 'build/kernel.elf', out / 'build/kernel.elf')
        record['kernel_reuse'] = str(reuse_kernel)

    kernel = image(out / 'build/kernel.elf', 0x80400000, 0x4000000)
    record['kernel'] = kernel
    users = []
    for index, program in enumerate(programs):
        for name in program['sources'] + program['assembly']:
            dst = out / name
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, dst)
        lines = ['format 1', 'profile suba-user', 'entry ' + program['entry']]
        lines += ['source ' + name for name in program['sources']]
        lines += ['assembly ' + name for name in program['assembly']]
        lines += [f'output build/user{index}.elf']
        (out / f'user{index}.build').write_text('\n'.join(lines) + '\n')
        compile(f'user{index}.build')
        users.append(image(out / f'build/user{index}.elf', 0x10000, 0x4000000))
    record['users'] = users
    descriptor = bytearray(256)
    struct.pack_into('<QIIQQQ', descriptor, 0, 0x3154524154534253, 1, 256,
                     KERNEL_SOURCE, kernel['bytes'], len(users))
    sources = [(KERNEL_SOURCE, kernel['bytes'])]
    for index, user in enumerate(users):
        address = IMAGE_SOURCE + index * 0x400000
        struct.pack_into('<QQ', descriptor, 64 + index * 16, address, user['bytes'])
        sources.append((address, user['bytes']))
    previous = kernel['end']
    for address, length in sources:
        require(previous <= address and 0 < length <= 0x400000 and
                length <= 0xa0000000 - address, 'RAM fixture overlaps reserved input')
        previous = address + length
    (out / 'build/start.bin').write_bytes(descriptor)
    (out / 'config.vt').write_text('module test::config;\n'
        'pub const MAGIC: usize = 0x314f464e49425553;\n'
        f'pub const KERNEL_ENTRY: usize = {kernel["entry"]};\n'
        f'pub const KERNEL_END: usize = {kernel["end"]};\n')
    boot = (out / 'tests/k0/boot.vt').read_text()
    anchor = '    put(abi::BOOT_INFO_RESERVATION_COUNT, 1, 4);'
    extra = f'    put(abi::BOOT_INFO_RESERVATION_COUNT, {len(sources) + 1}, 4);\n'
    for index, (address, length) in enumerate(sources, 1):
        extra += f'    put(abi::BOOT_INFO_RESERVATIONS + {index * 16}_usize, {address}, 8);\n'
        extra += f'    put(abi::BOOT_INFO_RESERVATIONS + {index * 16 + 8}_usize, {(length + 4095) // 4096 * 4096}, 8);\n'
    require(boot.count(anchor) == 1, 'boot reservation observation anchor')
    (out / 'test_boot.vt').write_text(boot.replace(anchor, extra))
    (out / 'boot.build').write_text('format 1\nprofile suba-boot\nentry test::boot::start\n'
        'bind panic=test::boot::panic\nsource abi/contract.vt\nsource kernel/machine.vt\n'
        'source tests/k0/fw_cfg.vt\nsource test_boot.vt\nsource config.vt\n'
        'assembly kernel/machine.s0\noutput build/boot.elf\n')
    compile('boot.build')
    boot_meta = image(out / 'build/boot.elf', 0x80200000, 0x200000)
    require(boot_meta['end'] <= DESCRIPTOR, 'boot intersects descriptor')
    record['compiled_inputs'] = {str(path.relative_to(out)): sha(path)
        for path in out.rglob('*') if path.suffix in ('.vt', '.s0', '.build')}
    run = ['qemu-system-riscv64', '-machine', 'virt', '-m', '512M', '-smp', '1', '-nographic',
           '-bios', str(FIRMWARE), '-kernel', str(out / 'build/boot.elf'), '-device', 'ramfb',
           '-no-reboot', '-device', f'loader,file={out}/build/kernel.elf',
           '-device', f'loader,file={out}/build/kernel.elf,addr={KERNEL_SOURCE},force-raw=on',
           '-device', f'loader,file={out}/build/start.bin,addr={DESCRIPTOR},force-raw=on']
    for index, (address, length) in enumerate(sources[1:]):
        run += ['-device', f'loader,file={out}/build/user{index}.elf,addr={address},force-raw=on']
    return run
