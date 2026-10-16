#!/usr/bin/env python3
"""Build and run actual U-mode K3 fixtures; retain every input and observed verdict."""
import argparse
import json
import re
from pathlib import Path
import shutil
import struct
from check_k2 import command, sha, DESCRIPTOR, KERNEL_SOURCE, IMAGE_SOURCE
from check_kernel_entry import image, observe, FIRMWARE, require
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--case',default='smoke')
    parser.add_argument('--require-slice-target',action='store_true',help='also require measured dispatch slice <=5ms')
    parser.add_argument('--mutation',choices=['none','allocation-0','allocation-1','allocation-2','omit-prune','late-token','omit-token-revocation','prefix-only-usercopy','cancel-reservation','cancel-install'],default='none')
    args=parser.parse_args()
    compiler=args.compiler.resolve();out=args.out.resolve()
    require((ROOT/'tests/k3'/f'{args.case}.vt').is_file(),'unknown fixture')
    out.mkdir(parents=True,exist_ok=False)
    for name in ['abi','kernel','platform','tests/k0','tests/k3','user/libsuba']:
        shutil.copytree(ROOT/name,out/name)
    (out/'build').mkdir()
    record=dict(case=args.case,mutation=args.mutation,compiler_sha256=sha(compiler),passed=False,commands=[])
    def compile(path):command(['qemu-riscv64','-s','1048576',str(compiler),'build',path],out,record['commands'])
    try:
        entry=out/'kernel/entry.vt';source=entry.read_text()
        source=source.replace('static mut INFO:', 'static mut TEST_BASELINE: usize = 0;\nstatic mut INFO:')
        source=source.replace('        dispatch::sources(IMAGES);','        TEST_BASELINE = memory::stats().free;\n        dispatch::sources(IMAGES);')
        anchor='                process::Selection::Idle => {'
        require(source.count(anchor)==1,'idle test hook')
        source=source.replace(anchor,anchor+'''
                    if dispatch::quiescent() {
                        if memory::stats().free != TEST_BASELINE { let stopped: u32 = panic(90); return 0; }
                        machine::text("suba K3: reclaimed\\n");
                        machine::text("suba K3: max slice ticks ");
                        dispatch::number(dispatch::max_slice_ticks()); machine::text("\\n");
                        machine::text("suba K3: max slice kind ");
                        dispatch::number(dispatch::max_slice_kind()); machine::text("\\n");
                        machine::halt();
                    }''')
        entry.write_text(source)
        if args.mutation.startswith('allocation-'):
            owner=out/'kernel/space.vt';code=owner.read_text()
            code=code.replace('static mut RECORDS:', 'static mut TEST_BUDGET: usize = 0xffffffffffffffff;\nstatic mut TEST_STARTED: bool = false;\nstatic mut RECORDS:')
            code=code.replace('        if owner < CAPACITY {',
                '        if owner < CAPACITY && TEST_BUDGET != 0xffffffffffffffff_usize {\n'
                '            if TEST_BUDGET == 0_usize { return 0; }\n'
                '            TEST_BUDGET = TEST_BUDGET - 1_usize;\n        }\n        if owner < CAPACITY {',1)
            anchor='        if !live(id) { return MappingResult::Invalid; }'
            code=code.replace(anchor,anchor+'\n        if address >= abi::USER_PAGES_BASE && address < abi::USER_PAGES_END && !TEST_STARTED {\n'
                f'            TEST_STARTED = true; TEST_BUDGET = {args.mutation[-1]};\n        }}')
            owner.write_text(code)
        if args.mutation == 'omit-prune':
            owner=out/'kernel/space.vt';code=owner.read_text()
            anchor='if PAGE_INFO[(leaf - abi::RAM_BASE) / abi::PAGE_BYTES].children == 0_u32 {'
            require(code.count(anchor)==1,'prune mutation anchor')
            owner.write_text(code.replace(anchor,'if false {'))
        if args.mutation in ['late-token','omit-token-revocation']:
            call=out/'kernel/dispatch_call.vt';code=call.read_text()
            anchor='                                if !process::terminate(target, abi::CANCELLED) { return false; }'
            require(code.count(anchor)==1,'kill gate anchor')
            code=code.replace(anchor,anchor+"""
                                match request::peek(process::slot(target)) {
                                    request::Peek::Empty => {},
                                    request::Peek::Ready(work) => {
                                        if request::active(target, work.token) || !request::owns(target, work.token) ||
                                            usercopy::range(target, abi::USER_STACK_BASE, 1, true) { return false; }
                                        machine::text("suba K3: late delivery revoked\\n");
                                    }
                                }""")
            call.write_text(code)
            if args.mutation=='omit-token-revocation':
                owner=out/'kernel/request.vt'
                owner.write_text(owner.read_text().replace('return process::deliverable(id) && owns(id, token);','return owns(id, token);'))
        if args.mutation == 'cancel-reservation':
            owner=out/'kernel/dispatch_spawn.vt';code=owner.read_text()
            anchor='                next.phase = request::Preparation::Create;\n                return request::advance(work.owner, work.token, request::Operation::Preparing(next));'
            require(code.count(anchor)==1,'spawn reservation cancellation anchor')
            code=code.replace(anchor,'                next.phase = request::Preparation::Create;\n                if !request::advance(work.owner, work.token, request::Operation::Preparing(next)) { return false; }\n                if !ROOTS[process::slot(work.owner)] {\n                    if !process::terminate(work.owner, abi::CANCELLED) { return false; }\n                    machine::text("suba K3: unbound reservation cancelled\\n");\n                }\n                return true;')
            owner.write_text(code)
        if args.mutation == 'cancel-install':
            owner=out/'kernel/dispatch_spawn.vt';code=owner.read_text()
            anchor='        return request::advance(parent, work.token, request::Operation::Installing(make request::Installing {\n            child: child, reservation: reservation, index: inputs.index, stdout: inputs.stdout, stderr: inputs.stderr }));'
            require(code.count(anchor)==1,'spawn install cancellation anchor')
            code=code.replace(anchor,'        if !request::advance(parent, work.token, request::Operation::Installing(make request::Installing {\n            child: child, reservation: reservation, index: inputs.index, stdout: inputs.stdout, stderr: inputs.stderr })) { return false; }\n        if !ROOTS[process::slot(parent)] {\n            if !process::terminate(parent, abi::CANCELLED) { return false; }\n            machine::text("suba K3: uninstalled child reference cancelled\\n");\n        }\n        return true;')
            owner.write_text(code)
        if args.mutation == 'prefix-only-usercopy':
            owner=out/'kernel/usercopy.vt';code=owner.read_text()
            anchor='            remaining = remaining - step;'
            require(code.count(anchor)==1,'range validation mutation anchor')
            owner.write_text(code.replace(anchor,anchor+'\n            return true;'))
        compile('kernel/kernel.build')
        kernel=image(out/'build/kernel.elf',0x80400000,0x4000000);record['kernel']=kernel
        users=[]
        for index,fixture in enumerate([args.case,'worker']):
            names=['abi/contract.vt','abi/syscalls.vt','abi/argument_wire.vt',
                   'user/libsuba/syscall.vt','user/libsuba/services.vt','user/libsuba/arguments.vt',
                   'user/libsuba/argument_builder.vt',
                   f'tests/k3/{fixture}.vt']
            if (out/'tests/k3/common.vt').exists():names.append('tests/k3/common.vt')
            (out/f'user{index}.build').write_text('format 1\nprofile suba-user\nentry test::program::run\n'+
                ''.join('source '+name+'\n' for name in names)+
                f'assembly user/libsuba/syscall.s0\noutput build/user{index}.elf\n')
            compile(f'user{index}.build')
            users.append(image(out/f'build/user{index}.elf',0x10000,0x4000000))
        record['users']=users
        descriptor=bytearray(256)
        struct.pack_into('<QIIQQQ',descriptor,0,0x3154524154534253,1,256,KERNEL_SOURCE,kernel['bytes'],len(users))
        sources=[(KERNEL_SOURCE,kernel['bytes'])]
        for i,user in enumerate(users):
            address=IMAGE_SOURCE+i*0x400000
            struct.pack_into('<QQ',descriptor,64+i*16,address,user['bytes']);sources.append((address,user['bytes']))
        previous=kernel['end']
        for address,length in sources:
            require(previous<=address and 0<length<=0x400000 and length<=0xa0000000-address,'source range/overlap')
            previous=address+length
        (out/'build/start.bin').write_bytes(descriptor)
        (out/'config.vt').write_text('module test::config;\npub const MAGIC: usize = 0x314f464e49425553;\n'+
            f'pub const KERNEL_ENTRY: usize = {kernel["entry"]};\npub const KERNEL_END: usize = {kernel["end"]};\n')
        boot=(out/'tests/k0/boot.vt').read_text()
        anchor='    put(abi::BOOT_INFO_RESERVATION_COUNT, 1, 4);'
        extra=f'    put(abi::BOOT_INFO_RESERVATION_COUNT, {len(sources)+1}, 4);\n'
        for i,(address,length) in enumerate(sources,1):
            extra+=f'    put(abi::BOOT_INFO_RESERVATIONS + {i*16}_usize, {address}, 8);\n'
            extra+=f'    put(abi::BOOT_INFO_RESERVATIONS + {i*16+8}_usize, {(length+4095)//4096*4096}, 8);\n'
        require(boot.count(anchor)==1,'boot reservation anchor')
        (out/'tests/k3/boot.vt').write_text(boot.replace(anchor,extra))
        (out/'boot.build').write_text('format 1\nprofile suba-boot\nentry test::boot::start\n'+
            'bind panic=test::boot::panic\nsource abi/contract.vt\nsource kernel/machine.vt\n'+
            'source tests/k0/fw_cfg.vt\nsource tests/k3/boot.vt\nsource config.vt\n'+
            'assembly kernel/machine.s0\noutput build/boot.elf\n')
        compile('boot.build')
        boot_meta=image(out/'build/boot.elf',0x80200000,0x200000)
        require(boot_meta['end']<=DESCRIPTOR,'boot/stack/DTB intersects descriptor')
        require(sha(out/'build/kernel.elf')==kernel['sha256'],'kernel source changed')
        run=['qemu-system-riscv64','-machine','virt','-m','512M','-smp','1','-nographic',
             '-bios',str(FIRMWARE),'-kernel',str(out/'build/boot.elf'),'-device','ramfb','-no-reboot',
             '-device',f'loader,file={out}/build/kernel.elf',
             '-device',f'loader,file={out}/build/kernel.elf,addr={KERNEL_SOURCE},force-raw=on',
             '-device',f'loader,file={out}/build/start.bin,addr={DESCRIPTOR},force-raw=on']
        for i,(address,length) in enumerate(sources[1:]):
            run+=['-device',f'loader,file={out}/build/user{i}.elf,addr={address},force-raw=on']
        record['run_command']=run
        record['inputs']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ['.vt','.s0','.build']}
        panic={'omit-token-revocation':23,'prefix-only-usercopy':22}.get(args.mutation)
        marker=f'suba kernel panic reason={panic}\n' if panic else 'suba K3: reclaimed\n'
        forbidden=['suba K3: reclaimed'] if panic else ['suba kernel panic','!000000']
        result=observe(run,marker,forbidden,timeout=90)
        record['observation']=result;(out/'serial.log').write_text(result['log'])
        require(result['passed'],'no clean resource baseline')
        exits=[line for line in result['log'].splitlines() if line.startswith('suba K3: root exit ')]
        if not panic:
            expected=15 if args.mutation=='omit-prune' else 0
            require(exits==[f'suba K3: root exit {expected}'],f'user assertions failed: {exits}')
        if args.mutation=='late-token':
            require('suba K3: late delivery revoked' in result['log'],'no pending request cancellation observed')
        if args.mutation=='cancel-reservation':
            require('suba K3: unbound reservation cancelled' in result['log'],'reservation window not reached')
        if args.mutation=='cancel-install':
            require('suba K3: uninstalled child reference cancelled' in result['log'],'install window not reached')
        ticks=re.search(r'suba K3: max slice ticks (\d+)',result['log'])
        kind=re.search(r'suba K3: max slice kind (\d+)',result['log'])
        record['timing']=dict(timebase_hz=10000000,target_ticks=50000,
            max_dispatch_ticks=int(ticks[1]) if ticks else None,
            max_dispatch_kind=int(kind[1]) if kind else None,
            dispatch_target_met=int(ticks[1])<=50000 if ticks else None,
            continuous_supervisor_residency_measured=False,
            irq_service_latency_measured=False,two_compiler_background_measured=False)
        if args.require_slice_target:
            require(record['timing']['dispatch_target_met'] is True,'5ms dispatch slice target not met')
        record['passed']=True
    finally:
        (out/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(passed=True,record=str(out/'verification.json'))))
if __name__=='__main__':main()
