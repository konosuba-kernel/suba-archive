#!/usr/bin/env python3
"""Build separate boot/kernel ELFs with Q, observe their real S-mode handoff.

The boot source is a K0 RAM fixture, not the K1 disk stage0. QEMU preloads kernel.
No host assembler/linker patches any ELF. Observation ends the deliberately halted VM.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = Path('/usr/share/qemu/opensbi-riscv64-generic-fw_dynamic.bin')
FILES = ['abi/contract.vt', 'kernel/entry.vt', 'kernel/machine.vt', 'kernel/machine.s0',
         'kernel/kernel.build', 'kernel/memory.vt', 'platform/boot_info.vt', 'platform/fdt.vt',
         'platform/fdt_tree.vt', 'platform/fdt_properties.vt', 'kernel/ram.vt', 'tests/k0/boot.vt', 'tests/k0/fw_cfg.vt']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def image(path, base, window):
    data = path.read_bytes()
    require(data[:7] == b'\x7fELF\x02\x01\x01', 'invalid ELF identity')
    require(struct.unpack_from('<H', data, 18)[0] == 243, 'wrong ELF machine')
    entry, phoff = struct.unpack_from('<QQ', data, 24)
    phsize, count = struct.unpack_from('<HH', data, 54)
    require(phsize == 56 and count == 3, 'expected three load segments')
    end = base
    for i in range(3):
        kind, flags, offset, va, pa, size, memory, align = struct.unpack_from('<IIQQQQQQ', data, phoff+i*56)
        require(kind == 1 and flags == [5, 4, 6][i] and va == pa, 'bad segment policy')
        require(base <= va < base+window and memory <= base+window-va, 'segment outside profile')
        require(size <= memory and offset+size <= len(data) and va >= end, 'bad segment extent')
        require(align == 4096 and va % align == offset % align, 'bad alignment')
        if i == 0:
            require(va == base and entry == base, 'entry must be first load byte')
        end = va+memory
    return {'entry': entry, 'end': end, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def terminal_matches(text, path):
    """Require one boot handoff followed by exactly one complete allowed outcome."""
    events = [line for line in text.splitlines() if line.startswith(('suba ', '!'))]
    if len(events) != 2 or events[0] != 'suba K0 boot: entering kernel':
        return False
    if path == 'valid':
        return events[1] == 'suba kernel K0: handoff accepted'
    if path == 'bad-magic':
        return events[1] == 'suba kernel panic reason=1'
    if path == 'trusted-fault':
        return re.fullmatch(r'!0000000000000002:[0-9a-f]{16}:[0-9a-f]{16}', events[1]) is not None
    raise ValueError('unknown terminal path')


def observe(command, marker, forbidden, timeout=20):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    data = bytearray()
    deadline = time.monotonic()+timeout
    observed = False
    stable = False
    marker_time = None
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], 0.2)
            if ready:
                block = os.read(process.stdout.fileno(), 8192)
                if not block:
                    break
                data.extend(block)
            if marker.encode() in data and marker_time is None:
                observed = True
                marker_time = time.monotonic()
            # Keep collecting after an unexpected marker: UART writes may split a
            # fatal record across reads. The final verdict still rejects it.
            if process.poll() is not None:
                break
            if marker_time is not None and time.monotonic() - marker_time >= 0.5:
                stable = True
                break
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            tail, _ = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            tail, _ = process.communicate()
        data.extend(tail)
    text = data.decode(errors='replace')
    return {'command': command, 'marker': marker, 'observed': observed,
            'stable_observation_ms': 500 if stable else 0,
            'observer_stopped_after_marker': observed and stable, 'returncode': process.returncode,
            'log': text, 'passed': observed and stable and not any(value in text for value in forbidden)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    compiler = args.compiler.resolve()
    snapshot = {name: (ROOT/name).read_bytes() for name in FILES}
    report = {'passed': False, 'compiler_sha256': hashlib.sha256(compiler.read_bytes()).hexdigest(),
              'input_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in snapshot.items()},
              'firmware_sha256': hashlib.sha256(FIRMWARE.read_bytes()).hexdigest(), 'cases': [],
              'scope': 'K0 RAM handoff and early trusted panic only; not K1 disk loader or K2 user isolation'}
    def build(work, manifest):
        command = ['qemu-riscv64', '-s', '1048576', str(compiler), 'build', manifest]
        result = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=120)
        item = {'command': command, 'cwd': str(work), 'exit': result.returncode,
                'stdout': result.stdout, 'stderr': result.stderr}
        require(result.returncode == 0, str(item))
        return item
    try:
        for name in ['valid', 'bad-magic', 'trusted-fault', 'post-marker-fault']:
            work = out/name
            for path, data in snapshot.items():
                dest = work/path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            (work/'build').mkdir()
            item = {'name': name, 'commands': []}
            report['cases'].append(item)
            if name in ['trusted-fault', 'post-marker-fault']:
                path = work/'kernel/entry.vt'
                data = path.read_text().replace('fn prepare_memory(', 'extern abi(C) fn __k0_fault() -> ();\n\nfn prepare_memory(')
                before = '    let result: u32 = prepare_memory(info);' if name == 'trusted-fault' else '    machine::halt();'
                require(before in data, 'fault injection site missing')
                path.write_text(data.replace(before, '    unsafe { __k0_fault(); }\n'+before, 1))
                with (work/'kernel/machine.s0').open('a') as f:
                    f.write('\n# Test-only trusted exception injection.\n__k0_fault:\nunimp\njalr x0, 0(x1)\n')
            item['commands'].append(build(work, 'kernel/kernel.build'))
            item['kernel'] = image(work/'build/kernel.elf', 0x80400000, 0x4000000)
            magic = 0 if name == 'bad-magic' else 0x314f464e49425553
            (work/'config.vt').write_text('module test::config;\n'
                f'pub const MAGIC: usize = {magic};\n'
                f'pub const KERNEL_END: usize = {item["kernel"]["end"]};\n'
                f'pub const KERNEL_ENTRY: usize = {item["kernel"]["entry"]};\n')
            (work/'boot.build').write_text('format 1\nprofile suba-boot\nentry test::boot::start\n'
                'bind panic=test::boot::panic\nsource abi/contract.vt\nsource kernel/machine.vt\n'
                'source tests/k0/boot.vt\nsource tests/k0/fw_cfg.vt\nsource config.vt\nassembly kernel/machine.s0\noutput build/boot.elf\n')
            item['commands'].append(build(work, 'boot.build'))
            item['boot'] = image(work/'build/boot.elf', 0x80200000, 0x200000)
            expected_path = 'valid' if name == 'post-marker-fault' else name
            marker = {'valid': 'suba kernel K0: handoff accepted\n',
                      'bad-magic': 'suba kernel panic reason=1\n', 'trusted-fault': '!0000000000000002:'}[expected_path]
            forbidden = {
                'valid': ('suba kernel panic', 'suba K0 boot panic', '!'),
                'bad-magic': ('handoff accepted', 'suba K0 boot panic', '!'),
                'trusted-fault': ('suba kernel', 'suba K0 boot panic'),
            }[expected_path]
            command = ['qemu-system-riscv64', '-machine', 'virt', '-accel', 'tcg', '-m', '512M',
                       '-smp', '1', '-nographic', '-bios', str(FIRMWARE), '-kernel', str(work/'build/boot.elf'),
                       '-device', f'loader,file={work}/build/kernel.elf', '-device', 'ramfb', '-no-reboot']
            item['execution'] = observe(command, marker, forbidden)
            item['execution']['terminal_matches'] = terminal_matches(item['execution']['log'], expected_path)
            item['execution']['passed'] = item['execution']['passed'] and item['execution']['terminal_matches']
            item['expected_execution_passed'] = name != 'post-marker-fault'
            (work/'serial.log').write_text(item['execution']['log'])
            require(item['execution']['passed'] == item['expected_execution_passed'],
                    f'{name}: terminal observation misclassified; see serial.log')
            if name == 'post-marker-fault':
                log = item['execution']['log']
                require(marker in log and '!0000000000000002:' in log
                        and log.index(marker) < log.index('!0000000000000002:'),
                        'negative control must actually reach success then illegal-instruction fault')
            require('suba K0 boot: entering kernel' in item['execution']['log'], 'kernel reached without boot marker')
            item['passed'] = True
        report['passed'] = True
    finally:
        (out/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'passed': True, 'cases': len(report['cases']), 'record': str(out/'verification.json')}))


if __name__ == '__main__':
    main()
