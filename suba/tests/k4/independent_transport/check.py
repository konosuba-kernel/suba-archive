#!/usr/bin/env python3
"""Independent RAM-backed ring validation; complements real IRQ device runs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--omit-duplicate-guard', action='store_true')
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    candidate = ROOT / 'docs/workflows/through-k7/K4-transport-candidate-r1.json'
    record = json.loads(candidate.read_text())
    assert sha(candidate) == 'fd2845d4ef845db84e8188c9fd78cc5c468709e21597f954d3542027c43ea0ac'
    for name, digest in {**record['owned_files'], **record['inputs']}.items():
        assert sha(ROOT / name) == digest, name
    assert sha(compiler) == record['compiler_sha256']
    names = ['kernel/device/io.vt', 'kernel/device/io.s0', 'kernel/device/virtio.vt',
             'kernel/machine.vt', 'kernel/machine.s0', 'tests/k4/transport/shutdown.s0',
             'tests/k4/independent_transport/probe.vt']
    inputs = {}
    for name in names:
        dst = out / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dst)
        inputs[name] = sha(dst)
    if args.omit_duplicate_guard:
        path = out / 'kernel/device/virtio.vt'
        old = 'if ((*q).outstanding & bit) != 0_usize { return false; }'
        value = path.read_text()
        assert value.count(old) == 1
        path.write_text(value.replace(old, '// Independent negative control: omit duplicate publish guard.'))
    manifest = ['format 1', 'profile suba-kernel', 'entry acceptance::transport::start',
                'bind panic=acceptance::transport::panic', 'bind trap_dispatch=acceptance::transport::trap']
    manifest += ['source ' + n for n in names if n.endswith('.vt')]
    manifest += ['assembly ' + n for n in names if n.endswith('.s0')]
    manifest += ['output probe.elf']
    (out / 'probe.build').write_text('\n'.join(manifest) + '\n')
    command = ['qemu-riscv64', '-s', '1048576', str(compiler), 'build', 'probe.build']
    result = subprocess.run(command, cwd=out, capture_output=True, timeout=120)
    (out / 'compile.log').write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    firmware = Path('/usr/share/qemu/opensbi-riscv64-generic-fw_dynamic.bin')
    command = ['qemu-system-riscv64', '-machine', 'virt', '-m', '512M', '-smp', '1',
               '-nographic', '-bios', str(firmware), '-kernel', str(out / 'probe.elf'), '-no-reboot']
    timed_out = False
    try:
        run = subprocess.run(command, capture_output=True, timeout=4 if args.omit_duplicate_guard else 10)
        log = run.stdout + run.stderr
        exit_code = run.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        log = (error.stdout or b'') + (error.stderr or b'')
        exit_code = None
    (out / 'boot.log').write_bytes(log)
    passed = not timed_out and exit_code == 0 and b'independent transport boundaries PASS' in log and b'FAIL' not in log
    if args.omit_duplicate_guard:
        passed = timed_out and b'independent transport FAIL 00000019' in log and b'boundaries PASS' not in log
    evidence = dict(candidate_sha256=sha(candidate), inputs=inputs, compiler_sha256=sha(compiler),
                    firmware_sha256=sha(firmware), elf_sha256=sha(out/'probe.elf'), command=command,
                    mutant=args.omit_duplicate_guard, timed_out=timed_out,
                    compiled_transport_sha256=sha(out/'kernel/device/virtio.vt'),
                    exit=exit_code, log_sha256=sha(out/'boot.log'), passed=passed)
    (out / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
    assert passed, log[-1000:]
    print('Independent transport duplicate-guard negative PASS' if args.omit_duplicate_guard else
          'Independent transport boundaries PASS')

if __name__ == '__main__':
    main()
