#!/usr/bin/env python3
"""Feed independently malformed files to the actual ELF decoder under Linux."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    compiler=args.compiler.resolve(); original=args.elf.read_bytes(); out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    names=['abi/contract.vt','kernel/memory.vt','platform/boot_info.vt','platform/fdt.vt',
           'platform/fdt_tree.vt','platform/fdt_properties.vt','kernel/ram.vt','kernel/space.vt',
           'abi/image.vt','tests/k2/elf_probe.vt']
    for name in names:
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    for name in ['linux.vt','linux.s0']:
        shutil.copyfile(ROOT.parent/'biomiya/compiler/runtime'/name,out/name)
    (out/'probe.build').write_text('format 1\nprofile linux-user\nentry test::elf_probe::run\n'+
        ''.join('source '+name+'\n' for name in names)+'source linux.vt\nassembly linux.s0\noutput probe.elf\n')
    record=dict(compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
                valid_elf_sha256=hashlib.sha256(original).hexdigest(),passed=False,cases=[])
    try:
        build=subprocess.run(['qemu-riscv64','-s','1048576',str(compiler),'build','probe.build'],cwd=out,
                             capture_output=True,text=True,timeout=240)
        record['build']=dict(returncode=build.returncode,stdout=build.stdout,stderr=build.stderr)
        if build.returncode:raise RuntimeError(build.stderr)
        tests=[('valid',original,0)]
        for length in [0,1,15,63,64,64+56*3-1]:
            tests.append((f'truncated-{length}',original[:length],1))
        def corrupt(name,offset,value,width=8):
            data=bytearray(original);data[offset:offset+width]=value.to_bytes(width,'little')
            if offset in [64+16,64+2*56+16]:
                data[offset+8:offset+16]=value.to_bytes(8,'little')
            tests.append((name,bytes(data),1))
        corrupt('elf32',4,1,1);corrupt('big-endian',5,2,1);corrupt('not-executable',16,3,2)
        corrupt('wrong-machine',18,62,2);corrupt('wrong-version',20,2,4);corrupt('float-abi',48,4,4)
        corrupt('wrong-header-size',52,63,2);corrupt('wrong-program-size',54,55,2)
        corrupt('empty-program-table',56,0,2);corrupt('too-many-programs',56,9,2)
        corrupt('program-offset-wrap',32,2**64-16);corrupt('program-in-header',32,8)
        corrupt('unknown-program-type',64,2,4);corrupt('rwx',68,7,4);corrupt('write-only',68,2,4)
        corrupt('bad-align',64+48,2048);corrupt('offset-misaligned',64+8,4097)
        corrupt('physical-mismatch',64+24,0x20000);corrupt('below-user-base',64+16,0)
        corrupt('outside-user-window',64+2*56+16,0x5000000);corrupt('memory-overflow',64+40,2**64-1)
        corrupt('filesize-overflow',64+32,2**64-1);corrupt('file-offset-outside',64+8,0xfffffffffffff000)
        corrupt('empty-segment',64+40,0);corrupt('entry-unmapped',24,0);corrupt('entry-misaligned',24,0x10001)
        ro=struct.unpack_from('<Q',original,64+56+16)[0]
        corrupt('entry-read-only',24,ro)
        data=bytearray(original);struct.pack_into('<QQ',data,64+56+16,0x10000,0x10000)
        tests.append(('overlapping-segments',bytes(data),1))
        corrupt('filesize-greater-than-memory',64+32,struct.unpack_from('<Q',original,64+40)[0]+1)
        data=bytearray(original);struct.pack_into('<Q',data,64+8,0xfffffffffffff000);struct.pack_into('<Q',data,64+32,0)
        tests.append(('near-max-total',bytes(data),1))
        for name,data,want in tests:
            (out/'input.elf').write_bytes(data)
            command=['qemu-riscv64','-s','1048576',str(out/'probe.elf')]
            if name=='near-max-total':command.append('max-total')
            run=subprocess.run(command,cwd=out,
                               capture_output=True,text=True,timeout=30)
            record['cases'].append(dict(name=name,expected=want,actual=run.returncode,
                                       input_sha256=hashlib.sha256(data).hexdigest(),stderr=run.stderr))
            if run.returncode!=want:raise RuntimeError(f'{name}: expected {want}, got {run.returncode}')
        record['inputs']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in names}
        record['passed']=True
    finally:
        (out/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(record['cases']),record=str(out/'verification.json'))))

if __name__=='__main__':main()
