#!/usr/bin/env python3
"""Measure actual compiler layouts in a labelled test copy, without exposing production fields."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    compiler = args.compiler.resolve()
    out.mkdir(parents=True, exist_ok=False)
    names = ['abi/contract.vt', 'abi/argument_wire.vt', 'kernel/memory.vt', 'platform/boot_info.vt',
             'platform/fdt.vt', 'platform/fdt_tree.vt', 'platform/fdt_properties.vt',
             'kernel/ram.vt', 'kernel/space.vt', 'abi/image.vt', 'kernel/loader.vt', 'kernel/process.vt']
    inputs = {}
    for name in names:
        source = ROOT/name
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        inputs[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    # These sizeof accessors exist only in this test copy; no lifecycle code is changed.
    for name, declarations in {
        'space': ['pub fn measured_owned() -> usize { return sizeof(Owned); }',
                  'pub fn measured_record() -> usize { return sizeof(Record); }'],
        'process': ['pub fn measured_record() -> usize { return sizeof(Record); }']
    }.items():
        path = out/f'kernel/{name}.vt'
        path.write_text(path.read_text()+'\n'+'\n'.join(declarations)+'\n')
    for name in ['linux.vt', 'linux.s0']:
        shutil.copyfile(ROOT.parent/'biomiya/compiler/runtime'/name, out/name)
    (out/'probe.vt').write_text('''module test::cost;
import kernel::space;
import kernel::process;
import kernel::memory;
import runtime::linux;
pub fn run() -> u32 {
    let values: [4]usize = [space::measured_owned(), space::measured_record(),
        process::measured_record(), sizeof(memory::Frame)];
    var bytes: [32]u8 = zero;
    var i: usize = 0;
    unsafe {
        while i < 32_usize {
            bytes[i] = ((values[i / 8_usize] >> ((i % 8_usize) * 8_usize)) & 255_usize) as u8;
            i = i + 1_usize;
        }
        match linux::write_all(1, core::slice_of(bytes)) {
            linux::WriteResult::Done => { return 0; },
            linux::WriteResult::Failed(error) => { return 1; }
        }
    }
}
''')
    (out/'probe.build').write_text('format 1\nprofile linux-user\nentry test::cost::run\n'+
        ''.join('source '+name+'\n' for name in names)+
        'source linux.vt\nsource probe.vt\nassembly linux.s0\noutput probe.elf\n')
    build = subprocess.run(['qemu-riscv64','-s','1048576',str(compiler),'build','probe.build'],
                           cwd=out, capture_output=True, text=True, timeout=240)
    record = dict(inputs=inputs, compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
                  build=dict(code=build.returncode, stdout=build.stdout, stderr=build.stderr), passed=False)
    try:
        if build.returncode: raise RuntimeError(build.stderr)
        run = subprocess.run(['qemu-riscv64',str(out/'probe.elf')], capture_output=True, timeout=30)
        if run.returncode or len(run.stdout)!=32: raise RuntimeError(repr(run))
        record['bytes'] = dict(zip(['owned','space_record','process_record','frame'], struct.unpack('<4Q',run.stdout)))
        record['passed'] = True
    finally:
        (out/'verification.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record['bytes']))


if __name__ == '__main__':
    main()
