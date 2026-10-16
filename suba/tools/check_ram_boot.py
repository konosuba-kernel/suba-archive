#!/usr/bin/env python3
"""Check real RAM admission and reserved holes through the fixed QEMU/OpenSBI boot path."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from check_kernel_entry import FILES, FIRMWARE, image, observe, require

ROOT = Path(__file__).resolve().parents[1]
PROBE = 'tests/k2_ram/memory_probe.vt'
CASES = ['valid', 'reserved-holes', 'bad-dtb', 'bad-info', 'omit-fdt-reservations', 'omit-clear']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(command, work):
    result = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=120)
    record = dict(command=command, cwd=str(work), exit=result.returncode,
                  stdout=result.stdout, stderr=result.stderr)
    require(result.returncode == 0, str(record))
    return record


def replace(path, old, new):
    text = path.read_text()
    require(text.count(old) == 1, f'{path}: unique injection anchor missing')
    path.write_text(text.replace(old, new, 1))


def make_dtb(out):
    command = ['qemu-system-riscv64', '-machine', f'virt,dumpdtb={out}/raw.dtb',
               '-m', '512M', '-smp', '1', '-nographic', '-device', 'ramfb', '-bios', str(FIRMWARE)]
    records = [run(command, out)]
    records.append(run(['dtc', '-I', 'dtb', '-O', 'dts', 'raw.dtb', '-o', 'raw.dts'], out))
    source = (out/'raw.dts').read_text().replace('/dts-v1/;',
        '/dts-v1/;\n/memreserve/ 0x81001003 0x1001;', 1)
    source += '\n/ { reserved-memory { #address-cells = <2>; #size-cells = <2>; ranges;\n'
    source += 'review-hole@81202005 { reg = <0 0x81202005 0 0x2000>; no-map; };\n}; };\n'
    (out/'reserved.dts').write_text(source)
    records.append(run(['dtc', '-I', 'dts', '-O', 'dtb', 'reserved.dts', '-o', 'reserved.dtb'], out))
    return records


def configure_kernel(work, holes):
    replace(work/'kernel/entry.vt', 'import kernel::machine;',
            'import kernel::machine;\nimport test::memory_kernel;')
    anchor = '    // SAFETY: static diagnostic bytes remain valid throughout the synchronous write.\n'
    replace(work/'kernel/entry.vt', anchor,
            '    // Test-only page lifecycle and reserved-hole probe.\n'
            '    unsafe {\n        let result: u32 = memory_kernel::run();\n'
            '        if result != 0_u32 { return panic(result); }\n'
            '        machine::text("suba K2b RAM: verified\\n");\n    }\n'+anchor)
    replace(work/'kernel/kernel.build', 'output build/kernel.elf',
            f'source {PROBE}\nsource ram_config.vt\noutput build/kernel.elf')
    # These constants do not introduce data objects or alter instruction count.
    # The second build must retain exactly the same memory end as the sizing build.
    write_ram_config(work, holes, 0x80800000)


def write_ram_config(work, holes, end):
    first = (end+4095)//4096*4096
    pages = (0xa0000000-first)//4096-(6 if holes else 0)
    until = 0x81404000 if holes else first+3*4096
    (work/'ram_config.vt').write_text('module test::ram_config;\n'
        f'pub const FIRST_PAGE: usize = {first};\n'
        f'pub const EXPECTED_PAGES: usize = {pages};\n'
        f'pub const HOLES: bool = {str(holes).lower()};\n'
        f'pub const PROBE_UNTIL: usize = {until};\n')


def boot_source(work, name, holes, kernel):
    (work/'config.vt').write_text('module test::config;\n'
        'pub const MAGIC: usize = 0x314f464e49425553;\n'
        f'pub const KERNEL_END: usize = {kernel["end"]};\n'
        f'pub const KERNEL_ENTRY: usize = {kernel["entry"]};\n')
    p = work/'tests/k0/boot.vt'
    anchor = '    // SAFETY: kernel ELF is preloaded by the test harness.'
    if holes:
        replace(p, 'put(abi::BOOT_INFO_RESERVATION_COUNT, 1, 4);',
                'put(abi::BOOT_INFO_RESERVATION_COUNT, 2, 4);')
        replace(p, anchor,
                '    put(abi::BOOT_INFO_RESERVATIONS + 16_usize, 0x81403007, 8);\n'
                '    put(abi::BOOT_INFO_RESERVATIONS + 24_usize, 1, 8);\n'+anchor)
    if name == 'bad-dtb':
        replace(p, anchor, '    unsafe { DTB[0_usize] = 0_u8; }\n'+anchor)
    if name == 'bad-info':
        replace(p, anchor, '    put(76, 1, 1);\n'+anchor)
    (work/'boot.build').write_text('format 1\nprofile suba-boot\nentry test::boot::start\n'
        'bind panic=test::boot::panic\nsource abi/contract.vt\nsource kernel/machine.vt\n'
        'source tests/k0/boot.vt\nsource tests/k0/fw_cfg.vt\nsource config.vt\n'
        'assembly kernel/machine.s0\noutput build/boot.elf\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    compiler, out = args.compiler.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    snapshot = {p: (ROOT/p).read_bytes() for p in FILES+[PROBE]}
    report = dict(passed=False, compiler_sha256=sha(compiler.read_bytes()),
        input_sha256={p:sha(b) for p,b in snapshot.items()}, cases=[],
        tool_sha256=sha(Path(__file__).read_bytes()),
        firmware_sha256=sha(FIRMWARE.read_bytes()),
        scope='fixed 512 MiB RAM admission, no page tables or user isolation')
    try:
        report['dtb_commands'] = make_dtb(out)
        report['reserved_dtb_sha256'] = sha((out/'reserved.dtb').read_bytes())
        for name in CASES:
            work = out/name
            for path,data in snapshot.items():
                p = work/path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            (work/'build').mkdir()
            holes = name in ['reserved-holes','omit-fdt-reservations']
            probe = name not in ['bad-dtb','bad-info']
            item = dict(name=name, commands=[])
            report['cases'].append(item)
            if probe:
                configure_kernel(work, holes)
            if name == 'omit-fdt-reservations':
                replace(work/'kernel/ram.vt', 'while i < tree.reserved_count {',
                        'while i < 0_usize {')
            if name == 'omit-clear':
                replace(work/'kernel/memory.vt', '        clear_page(index);',
                        '        // TEST COPY: omit clearing.')
            def build(manifest):
                item['commands'].append(run(['qemu-riscv64','-s','1048576',str(compiler),
                                             'build',manifest], work))
            build('kernel/kernel.build')
            kernel = image(work/'build/kernel.elf',0x80400000,0x4000000)
            if probe:
                write_ram_config(work, holes, kernel['end'])
                (work/'build/kernel.elf').rename(work/'build/sizing.elf')
                build('kernel/kernel.build')
                final = image(work/'build/kernel.elf',0x80400000,0x4000000)
                require(final['end']==kernel['end'],'sizing constants changed image memory end')
                kernel=final
            item['kernel']=kernel
            boot_source(work,name,holes,kernel)
            build('boot.build')
            item['boot']=image(work/'build/boot.elf',0x80200000,0x200000)
            item['case_inputs']={str(p.relative_to(work)):sha(p.read_bytes()) for p in work.rglob('*')
                                 if p.is_file() and p.suffix in ['.vt','.s0','.build']}
            command=['qemu-system-riscv64','-machine','virt','-accel','tcg','-m','512M','-smp','1',
                     '-nographic','-bios',str(FIRMWARE),'-kernel',str(work/'build/boot.elf'),
                     '-device',f'loader,file={work}/build/kernel.elf','-device','ramfb','-no-reboot']
            if holes:
                command += ['-dtb', str(out/'reserved.dtb')]
            reason={'bad-dtb':4,'bad-info':1,'omit-fdt-reservations':26,'omit-clear':24}.get(name)
            expected=['suba K0 boot: entering kernel']
            if reason is None:
                marker='suba kernel K0: handoff accepted\n'
                expected+=['suba K2b RAM: verified',marker.strip()]
                forbidden=('panic','!')
            else:
                marker=f'suba kernel panic reason={reason}\n'
                expected += [marker.strip()]
                forbidden = ('handoff accepted', 'RAM: verified', '!')
            item['execution']=observe(command,marker,forbidden,timeout=90)
            events=[s for s in item['execution']['log'].splitlines() if s.startswith(('suba ','!'))]
            item['events'] = events
            item['expected_events'] = expected
            item['passed']=item['execution']['passed'] and events==expected
            (work/'serial.log').write_text(item['execution']['log'])
            require(item['passed'],f'{name}: unexpected boot behavior')
            print(f'{name}: passed',flush=True)
        report['passed']=True
    finally:
        (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(CASES)} RAM admission QEMU scenarios passed')


if __name__=='__main__':
    main()
