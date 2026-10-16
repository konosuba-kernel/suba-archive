#!/usr/bin/env python3
"""Check the actual bounded FDT decoder through a Linux-only binary transport."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ['abi/contract.vt', 'platform/fdt.vt', 'platform/fdt_tree.vt', 'platform/fdt_properties.vt']
TRANSPORT = ['tests/fdt/probe.vt', 'tests/fdt/linux.s0']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def segments(path):
    data = path.read_bytes()
    offset = struct.unpack_from('<Q', data, 32)[0]
    width, count = struct.unpack_from('<HH', data, 54)
    result = []
    for index in range(count):
        kind, flags, _, address, _, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', data, offset+index*width)
        if kind == 1:
            result.append(dict(flags=flags, address=address, file_bytes=filesz, memory_bytes=memsz,
                               bss_bytes=memsz-filesz, alignment=align))
    return result


def stack_cost(path, folder):
    """Decode frames from this frozen backend's prologue; associate source declaration order.

    This is a measured build audit, not a universal RISC-V disassembler. A changed prologue
    or unexpected function count rejects the audit instead of guessing a stack bound.
    """
    functions = []
    for source in PRODUCTION+TRANSPORT[:1]:
        text = (folder/source).read_text()
        for match in re.finditer(r'(?m)^(?:pub )?(?:unsafe )?fn ([a-z_][a-z_0-9]*)\(', text):
            start = text.index('{', match.end())
            end, depth = start+1, 1
            while depth:
                if text[end]=='{': depth += 1
                if text[end]=='}': depth -= 1
                end += 1
            functions.append(dict(name=match[1], source=source, body=text[start+1:end-1]))
    data = path.read_bytes()
    header = struct.unpack_from('<Q', data, 32)[0]
    _, _, offset, base, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', data, header)
    words = struct.unpack('<'+'I'*(size//4), data[offset:offset+size])
    measured = []
    for index, word in enumerate(words):
        if word != 0x00010f13:  # addi x30,x2,0: save caller sp
            continue
        cursor, value = index+1, 0
        while cursor < len(words) and words[cursor] != 0x41f10133:  # sub x2,x2,x31
            instruction = words[cursor]
            opcode, rd, funct3, rs1 = instruction&127, (instruction>>7)&31, (instruction>>12)&7, (instruction>>15)&31
            if opcode != 19 or rd != 31:
                raise RuntimeError('unrecognized compiler prologue')
            immediate = instruction>>20
            if funct3 == 0 and rs1 in (0,31):
                if immediate&0x800: immediate -= 4096
                value = (0 if rs1==0 else value) + immediate
            elif funct3 == 1 and rs1==31 and immediate==12:
                value <<= 12
            else:
                raise RuntimeError('unrecognized frame constant')
            cursor += 1
        if cursor == len(words) or value <= 0 or value%16:
            raise RuntimeError('unrecognized frame size')
        measured.append((base+4*index,value))
    if len(measured) != len(functions):
        raise RuntimeError('source/function prologue count differs')
    names = {entry['name'] for entry in functions}
    entries = {}
    for function, (address, frame) in zip(functions, measured):
        body = re.sub(r'//[^\n]*', '', function.pop('body'))
        function.update(address=address, frame_bytes=frame,
                        calls=sorted(set(re.findall(r'\b([a-z_][a-z_0-9]*)\s*\(', body)) & names))
        entries[function['name']] = function

    def longest(name, ancestors=()):
        if name in ancestors:
            raise RuntimeError('recursive call graph cannot use this stack audit')
        children = [longest(child, ancestors+(name,)) for child in entries[name]['calls']]
        child_bytes, chain = max(children, default=(0,[]), key=lambda pair: pair[0])
        return entries[name]['frame_bytes']+child_bytes, [name]+chain

    total, chain = longest('inspect')
    return dict(method='exact RV64 prologue frame constants and direct source call graph; '
                       'no recursion, all production alignments <=16', functions=list(entries.values()),
                inspect_chain_bytes=total, inspect_chain=chain,
                excludes='caller frames outside inspect, firmware, interrupts and machine bridge')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    fixtures = ROOT/'tests/fdt'
    paths = [ROOT/name for name in PRODUCTION+TRANSPORT]
    paths += sorted(path for path in fixtures.iterdir() if path.is_file() and path not in paths)
    paths += [Path(__file__).resolve()]
    record = dict(compiler=str(compiler), compiler_sha256=digest(compiler),
                  inputs={str(path.relative_to(ROOT)): digest(path) for path in paths},
                  scope='production FDT decoder in Linux userspace, not kernel boot or RAM ownership',
                  builds=[], cases=[], negative_controls=[], passed=False)
    snapshot = out/'source'
    for path in paths:
        destination = snapshot/path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    spec = importlib.util.spec_from_file_location('fdt_cases', snapshot/'tests/fdt/cases.py')
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    all_cases = fixture_module.cases(snapshot/'tests/fdt')
    qemu = shutil.which('qemu-riscv64')
    dtc = shutil.which('dtc')
    if not qemu or not dtc:
        raise RuntimeError('qemu-riscv64 and dtc are required for this test driver')
    record['qemu'] = dict(path=qemu, sha256=digest(Path(qemu)))
    record['dtc'] = dict(path=dtc, sha256=digest(Path(dtc)))

    def build(name, mutation=None):
        folder = out/name
        shutil.copytree(snapshot, folder)
        if mutation:
            relative, old, new = mutation
            path = folder/relative
            text = path.read_text()
            if text.count(old) != 1:
                raise RuntimeError('mutation anchor must occur exactly once')
            path.write_text(text.replace(old, new))
        manifest = ('format 1\nprofile linux-user\nentry test::fdt::run\n' +
                    ''.join(f'source {source}\n' for source in PRODUCTION+TRANSPORT[:1]) +
                    'assembly tests/fdt/linux.s0\noutput probe.elf\n')
        (folder/'probe.build').write_text(manifest)
        command = [qemu, '-s', '1048576', str(compiler), 'build', 'probe.build']
        result = subprocess.run(command, cwd=folder, capture_output=True, timeout=120)
        evidence = dict(name=name, command=command, returncode=result.returncode,
                        stdout=result.stdout.decode(errors='replace'), stderr=result.stderr.decode(errors='replace'),
                        mutation=mutation, inputs={source:digest(folder/source) for source in PRODUCTION+TRANSPORT})
        record['builds'].append(evidence)
        if result.returncode != 0:
            raise RuntimeError(f'{name}: compiler failed: {evidence["stderr"]}')
        evidence['elf_sha256'] = digest(folder/'probe.elf')
        evidence['segments'] = segments(folder/'probe.elf')
        if mutation is None:
            evidence['stack_cost'] = stack_cost(folder/'probe.elf', folder)
        evidence['metrics'] = dict(re.findall(r'([a-z_]+)=([0-9]+)', evidence['stdout']+evidence['stderr']))
        return folder/'probe.elf'

    def execute(executable, case):
        command = [qemu, '-s', '1048576', str(executable)]
        result = subprocess.run(command, input=case['data'], capture_output=True, timeout=5)
        expected = b''
        if case['expected_exit'] == 0:
            expected = struct.pack('<QQQ', *fixture_module.RAM, len(case['regions']))
            expected += b''.join(struct.pack('<QQ', *region) for region in case['regions'])
        return dict(name=case['name'], command=command,
                    input_sha256=hashlib.sha256(case['data']).hexdigest(), input_bytes=len(case['data']),
                    expected_exit=case['expected_exit'], actual_exit=result.returncode,
                    expected_output_hex=expected.hex(), output_hex=result.stdout.hex(),
                    stderr=result.stderr.decode(errors='replace'),
                    passed=result.returncode==case['expected_exit'] and result.stdout==expected and not result.stderr)

    try:
        executable = build('production')
        input_folder = out/'inputs'
        input_folder.mkdir()
        for case in all_cases:
            input_path = input_folder/(case['name']+'.dtb')
            input_path.write_bytes(case['data'])
            evidence = execute(executable, case)
            if case['oracle']:
                command = [dtc, '-I', 'dtb', '-O', 'dts', str(input_path)]
                oracle = subprocess.run(command, capture_output=True, timeout=5)
                evidence['independent_dtc'] = dict(command=command, returncode=oracle.returncode,
                    stderr=oracle.stderr.decode(errors='replace'),
                    output_sha256=hashlib.sha256(oracle.stdout).hexdigest())
                evidence['passed'] = evidence['passed'] and oracle.returncode == 0
                input_path.with_suffix('.dts').write_bytes(oracle.stdout)
            record['cases'].append(evidence)
        failed = [case['name'] for case in record['cases'] if not case['passed']]
        if failed:
            raise RuntimeError('fixture failures: '+', '.join(failed))
        controls = [
            ('omit-reserved-reg', 'reserved-static', ('platform/fdt_properties.vt',
             'if equal(name, "reg") { return reservation_registers(node, value, output); }',
             'if equal(name, "reg") { let marked: bool = once(node, REG_SEEN); return Check::Good; }')),
            ('omit-reservation-map', 'reservation-map', ('platform/fdt.vt',
             'if base == 0_usize && bytes == 0_usize { return Check::Good; }',
             'return Check::Good; // TEST COPY: omit the entire reservation map.')),
            ('allow-stale-name', 'duplicate-memory', ('platform/fdt_tree.vt',
             'if (*tree).memory_seen { return Check::Invalid; }',
             '// TEST COPY: accept a duplicate root memory node.')),
        ]
        for name, case_name, mutation in controls:
            changed = build(name, mutation)
            selected = next(case for case in all_cases if case['name']==case_name)
            evidence = execute(changed, selected)
            evidence['control'] = name
            evidence['expected_defect_output_hex'] = struct.pack('<QQQ', *fixture_module.RAM, 0).hex()
            evidence['detected'] = (not evidence['passed'] and evidence['actual_exit'] == 0 and
                                    evidence['output_hex'] == evidence['expected_defect_output_hex'] and
                                    evidence['stderr'] == '')
            record['negative_controls'].append(evidence)
            if not evidence['detected']:
                raise RuntimeError(f'{name}: negative control was not distinguished')
        record['passed'] = True
    finally:
        (out/'verification.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(dict(passed=record['passed'], cases=len(record['cases']),
                         controls=len(record['negative_controls']), record=str(out/'verification.json'))))


if __name__ == '__main__':
    main()
