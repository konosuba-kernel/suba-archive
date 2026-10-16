#!/usr/bin/env python3
"""Build original S-next ELF images and verify protected K2 execution on fixed QEMU."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from check_kernel_entry import image, observe, FIRMWARE, require

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = 0x803f0000
KERNEL_SOURCE = 0x88000000
IMAGE_SOURCE = 0x88400000


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, cwd, record, timeout=240):
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        # Keep failed construction evidence as well as successful subprocesses.
        def decoded(value):
            return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
        record.append(dict(command=args, cwd=str(cwd), timeout_seconds=timeout,
                           stdout=decoded(error.stdout), stderr=decoded(error.stderr)))
        raise
    item = dict(command=args, cwd=str(cwd), code=result.returncode,
                stdout=result.stdout, stderr=result.stderr)
    record.append(item)
    require(result.returncode == 0, str(item))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', choices=['basic','registers','rollback','null','privileged','guard','text-write','ro-write','nx','kernel-read','s-firmware','s-text-write','s-guard','restore-negative','unknown-interrupt','bad-boot-info','bad-descriptor','bad-user-elf','load-no-memory'], default='basic')
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for name in ['kernel', 'abi', 'platform', 'tests/k0', 'tests/k2']:
        shutil.copytree(ROOT/name, out/name)
    (out/'build').mkdir()
    records = dict(case=args.case, compiler_sha256=sha(compiler), commands=[], passed=False)
    def compile(manifest):
        command(['qemu-riscv64','-s','1048576',str(compiler),'build',manifest],out,records['commands'])
    try:
        # K3 keeps a resident scheduler. This test-only adapter preserves the K2
        # two-root fixture and terminal free-page assertion without changing production.
        entry=out/'kernel/entry.vt'
        code=entry.read_text()
        if 'dispatch::sources(IMAGES)' in code:
            code=code.replace('static mut INFO:', 'static mut BASELINE: usize = 0;\nstatic mut INFO:')
            code=code.replace('        dispatch::sources(IMAGES);',
                '        BASELINE = memory::stats().free;\n        dispatch::sources(IMAGES);')
            code=code.replace('        if !dispatch::boot(0) { return panic(21); }',
                '        var test_index: usize = 0;\n        while test_index < IMAGES.count {\n'
                '            if !dispatch::boot(test_index) { machine::text("suba K2: image rejected\\n"); }\n'
                '            test_index = test_index + 1_usize;\n        }')
            code=code.replace('                process::Selection::Idle => {',
                '                process::Selection::Idle => {\n'
                '                    if dispatch::quiescent() {\n'
                '                        if memory::stats().free != BASELINE { let stopped: u32 = panic(17); return 0; }\n'
                '                        machine::text("suba K2: all pages reclaimed\\n"); machine::halt();\n'
                '                    }')
            code=code.replace('suba K3: user fault isolated', 'suba K2: user fault isolated')
            entry.write_text(code)
            dispatcher=out/'kernel/dispatch.vt'
            code=dispatcher.read_text().replace('machine::text("suba K3: root exit "); number(exit.status);',
                'machine::text("suba K2: exit "); number(exit.status); machine::text(" cause "); number(exit.cause);')
            dispatcher.write_text(code)
        if args.case in ['registers','restore-negative','unknown-interrupt']:
            entry=out/'kernel/entry.vt'
            code=entry.read_text().replace('import kernel::machine;', 'import kernel::machine;\nimport test::timer_probe;')
            code=code.replace('process::Event::Timer(id) => {},',
                'process::Event::Timer(id) => { if !timer_probe::tick(id) { let stopped: u32 = panic(80); return 0; } },')
            entry.write_text(code)
            manifest=out/'kernel/kernel.build'
            manifest.write_text(manifest.read_text().replace('source kernel/entry.vt',
                'source tests/k2/timer_probe.vt\nsource kernel/entry.vt'))
        if args.case == 'restore-negative':
            trap=out/'kernel/trap.s0'
            code=trap.read_text()
            require(code.count('ld x28, 216(x31)')==1,'x28 restore anchor')
            trap.write_text(code.replace('ld x28, 216(x31)', '# TEST NEGATIVE: x28 restoration removed'))
            records['mutation']='test copy omits x28 restore; register probe must reject'
        if args.case == 'unknown-interrupt':
            entry=out/'kernel/entry.vt'
            code=entry.read_text().replace('        match process::capture(frame) {',
                '        *core::ptr::<usize>(frame + 264_usize) = 0x8000000000000009;\n        match process::capture(frame) {')
            entry.write_text(code)
            records['mutation']='test copy injects unsupported external interrupt into saved frame'
        if args.case.startswith('s-'):
            address={'s-firmware':0x80000000,'s-text-write':0x80400000,'s-guard':0x70000000}[args.case]
            fault_address=address
            operation='sb x0, 0(x10)' if args.case=='s-text-write' else 'ld x5, 0(x10)'
            entry=out/'kernel/entry.vt'
            code=entry.read_text().replace('static mut INFO:', 'extern abi(C) fn __supervisor_probe(address: usize) -> ();\nstatic mut INFO:')
            code=code.replace('        BASELINE = memory::stats().free;',
                f'        BASELINE = memory::stats().free;\n        __supervisor_probe({address});')
            entry.write_text(code)
            trap=out/'kernel/trap.s0'
            trap.write_text(trap.read_text()+f'\n# TEST ONLY trusted S-mode access.\n__supervisor_probe:\n{operation}\njalr x0, 0(x1)\n')
        if args.case == 'load-no-memory':
            owner=out/'kernel/space.vt'
            owner.write_text(owner.read_text().replace('QUOTA_PAGES: usize = 24576;', 'QUOTA_PAGES: usize = 3;'))
            records['mutation']='test copy quota=3 forces loader NoMemory; production quota tested separately'
        if args.case == 'rollback':
            entry=out/'kernel/entry.vt'
            code=entry.read_text().replace('import kernel::machine;', 'import kernel::machine;\nimport test::rollback_probe;')
            code=code.replace('        BASELINE = memory::stats().free;',
                '        BASELINE = memory::stats().free;\n        if !rollback_probe::run(IMAGES.images[0_usize]) { return panic(81); }')
            entry.write_text(code)
            manifest=out/'kernel/kernel.build'
            manifest.write_text(manifest.read_text().replace('source kernel/entry.vt',
                'source tests/k2/rollback_probe.vt\nsource kernel/entry.vt'))
        compile('kernel/kernel.build')
        kernel = image(out/'build/kernel.elf',0x80400000,0x4000000)
        records['kernel'] = kernel
        users=[]
        for index in range(2):
            user_source=(out/'tests/k2/user.vt').read_text()
            extra=''
            if args.case in ['registers','restore-negative','unknown-interrupt']:
                user_source=('module test::user;\nextern abi(C) fn __probe() -> ();\n'
                             'pub fn run() -> u32 { unsafe { __probe(); } return 99; }\n')
                extra='__probe:\n'+''.join(f'addi x{r}, x0, {(index+1)*100+r}\n' for r in range(1,32))
                extra+='address x31, .forever\n.forever:\njalr x0, 0(x31)\n'
            elif args.case in ['null','privileged','guard','text-write','ro-write','nx','kernel-read'] and index == 0:
                user_source=('module test::user;\nstatic MESSAGE: []const u8 = "readonly";\n'
                             'static mut DATA: [8]u8 = zero;\n'
                             'extern abi(C) fn __probe(address: usize) -> ();\n'
                             'pub fn run() -> u32 { unsafe { __probe(')
                if args.case == 'ro-write':
                    user_source+='core::addr(MESSAGE.data)'
                    extra='__probe:\nsb x0, 0(x10)\njalr x0, 0(x1)\n'
                elif args.case == 'nx':
                    user_source+='core::addr(core::slice_of(DATA).data)'
                    extra='__probe:\njalr x0, 0(x10)\n'
                else:
                    target={'null':0,'privileged':0,'guard':0x3feff000,
                            'text-write':0x10000,'kernel-read':0x80400000}[args.case]
                    user_source+=str(target)
                    instruction={'null':'ld x5, 0(x10)', 'privileged':'csrrw x0, 384, x0',
                                 'guard':'ld x5, 0(x10)', 'text-write':'sb x0, 0(x10)',
                                 'kernel-read':'ld x5, 0(x10)'}[args.case]
                    extra=f'__probe:\n{instruction}\njalr x0, 0(x1)\n'
                user_source+='); } return 99; }\n'
            (out/f'user{index}.vt').write_text(user_source)
            (out/f'user{index}.s0').write_text((out/'tests/k2/user_exit.s0').read_text()+extra)
            (out/f'user{index}.build').write_text('format 1\nprofile suba-user\nentry test::user::run\n'
                f'source user{index}.vt\nassembly user{index}.s0\noutput build/user{index}.elf\n')
            compile(f'user{index}.build')
            users.append(image(out/f'build/user{index}.elf',0x10000,0x4000000))
        records['users']=users
        if args.case == 'bad-user-elf':
            path=out/'build/user0.elf'
            data=bytearray(path.read_bytes());struct.pack_into('<I',data,68,7);path.write_bytes(data)
            records['mutation']='test input ELF first PT_LOAD flags changed to RWX'
            records['mutated_user_sha256']=sha(path)
        # QEMU loads identical kernel ELF once as ELF and once as immutable raw input.
        descriptor = bytearray(256)
        struct.pack_into('<QIIQQQ', descriptor, 0, 0x3154524154534253, 1, 256,
                         KERNEL_SOURCE,(out/'build/kernel.elf').stat().st_size,2)
        sources = [(KERNEL_SOURCE,(out/'build/kernel.elf').stat().st_size)]
        for i in range(2):
            address = IMAGE_SOURCE+i*0x400000
            length = (out/f'build/user{i}.elf').stat().st_size
            struct.pack_into('<QQ', descriptor,64+i*16,address,length)
            sources.append((address,length))
        previous_end=kernel['end']
        for address,length in sources:
            require(address % 4096 == 0 and 0 < length <= 0x4000000,
                    'launch source alignment or length')
            require(previous_end <= address and address < 0xa0000000 and
                    length <= 0xa0000000-address, 'launch source overlap or RAM extent')
            previous_end=address+length
        if args.case == 'bad-descriptor':descriptor[0]=0
        (out/'build/start.bin').write_bytes(descriptor)
        records['launch_descriptor_sha256']=sha(out/'build/start.bin')
        records['sources']=[dict(address=a,bytes=n) for a,n in sources]
        # The exact same path is used by both loader devices below; no repacked ELF exists.
        require(sha(out/'build/kernel.elf')==kernel['sha256'],'kernel source identity changed')
        end = kernel['end']
        (out/'config.vt').write_text('module test::config;\n'
            f'pub const MAGIC: usize = {0 if args.case=="bad-boot-info" else 0x314f464e49425553};\n'
            f'pub const KERNEL_ENTRY: usize = {kernel["entry"]};\n'
            f'pub const KERNEL_END: usize = {end};\n')
        boot = (out/'tests/k0/boot.vt').read_text()
        anchor = '    put(abi::BOOT_INFO_RESERVATION_COUNT, 1, 4);'
        extra = f'    put(abi::BOOT_INFO_RESERVATION_COUNT, {len(sources)+1}, 4);\n'
        for i,(address,length) in enumerate(sources,1):
            extra += f'    put(abi::BOOT_INFO_RESERVATIONS + {i*16}_usize, {address}, 8);\n'
            extra += f'    put(abi::BOOT_INFO_RESERVATIONS + {i*16+8}_usize, {(length+4095)//4096*4096}, 8);\n'
        require(boot.count(anchor)==1,'boot reservation anchor')
        (out/'tests/k2/boot.vt').write_text(boot.replace(anchor,extra))
        (out/'boot.build').write_text('format 1\nprofile suba-boot\nentry test::boot::start\n'
            'bind panic=test::boot::panic\nsource abi/contract.vt\nsource kernel/machine.vt\n'
            'source tests/k0/fw_cfg.vt\nsource tests/k2/boot.vt\nsource config.vt\n'
            'assembly kernel/machine.s0\noutput build/boot.elf\n')
        compile('boot.build')
        boot_meta=image(out/'build/boot.elf',0x80200000,0x200000)
        require(boot_meta['end'] <= DESCRIPTOR,
                'boot ELF/BSS/stack/DTB overlaps launch descriptor')
        records['boot']=boot_meta
        run=['qemu-system-riscv64','-machine','virt','-m','512M','-smp','1','-nographic',
             '-bios',str(FIRMWARE),'-kernel',str(out/'build/boot.elf'),
             '-device',f'loader,file={out}/build/kernel.elf',
             '-device',f'loader,file={out}/build/kernel.elf,addr={KERNEL_SOURCE},force-raw=on',
             '-device',f'loader,file={out}/build/start.bin,addr={DESCRIPTOR},force-raw=on',
             '-device','ramfb','-no-reboot']
        for index,(address,length) in enumerate(sources[1:]):
            run += ['-device',f'loader,file={out}/build/user{index}.elf,addr={address},force-raw=on']
        records['run_command']=run
        # Full source hashes are recorded after all generated inputs exist.
        records['inputs']={str(p.relative_to(out)):sha(p) for p in out.rglob('*')
                           if p.suffix in ['.vt','.s0','.build']}
        expected_failure={
            's-firmware':'!000000000000000d:', 's-text-write':'!000000000000000f:',
            's-guard':'!000000000000000d:', 'restore-negative':'suba kernel panic reason=80\n',
            'unknown-interrupt':'suba kernel panic reason=10\n',
            'bad-boot-info':'suba kernel panic reason=1\n',
            'bad-descriptor':'suba kernel panic reason=8\n'}
        marker=expected_failure.get(args.case,'suba K2: all pages reclaimed\n')
        forbidden=['suba K2: all pages reclaimed','suba K2: user fault isolated'] if args.case in expected_failure else ['suba kernel panic','!000000']
        result=observe(run,marker,forbidden,timeout=30)
        records['observation']=result
        (out/'serial.log').write_text(result['log'])
        require(result['passed'],'protected execution marker or stable observation failed')
        serial=result['log']
        if args.case in expected_failure:
            if args.case.startswith('s-'):
                require(f':{fault_address:016x}\n' in serial,'supervisor fault stval must match target')
        elif args.case == 'load-no-memory':
            require(serial.count('suba K2: image rejected')==2,'both images hit creation failure')
            require(serial.count('suba K2: exit 7 cause 0')==2,'NoMemory status retained through reap')
        elif args.case == 'bad-user-elf':
            require(serial.count('suba K2: image rejected')==1,'malformed user ELF rejected')
            require(serial.count('suba K2: exit 0 cause 0')==1,'other image survives rejection')
        elif args.case in ['basic','registers','rollback']:
            require(serial.count('suba K2: exit 0 cause 0')==2,'both actual user processes must exit successfully')
            if args.case in ['registers','restore-negative','unknown-interrupt']:
                require(serial.count('suba K2: full frame preempted twice')==2,'both contexts must resume after timers')
        else:
            cause={'null':13,'privileged':2,'guard':13,'text-write':15,'ro-write':15,'nx':12,'kernel-read':13}[args.case]
            require(serial.count(f'suba K2: exit {128+cause} cause {cause}')==1,'fault cause must match hardware exception')
            require(serial.count('suba K2: exit 0 cause 0')==1,'unrelated process must survive')
            require(serial.count('suba K2: user fault isolated')==1,'fault must use application teardown')
        if args.case == 'rollback':
            require('suba K2: failed creation and quota reclaimed' in serial,'rollback/quota proof missing')
        records['passed']=True
    finally:
        (out/'verification.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps(dict(passed=True,record=str(out/'verification.json'))))


if __name__=='__main__':
    main()
