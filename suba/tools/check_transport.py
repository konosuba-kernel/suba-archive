#!/usr/bin/env python3
"""Check the shared transport on actual QEMU IRQs, FLUSH, restart and u16 wrap.

The fixed scratch addresses and supervisor test vector belong only to this probe;
production drivers must provide pinned DMA and the protected kernel IRQ dispatcher.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = Path('/usr/share/qemu/opensbi-riscv64-generic-fw_dynamic.bin')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--no-irq', action='store_true')
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    names = ['kernel/device/io.vt', 'kernel/device/io.s0', 'kernel/device/virtio.vt',
             'kernel/machine.vt', 'kernel/machine.s0', 'tests/k4/transport/block_probe.vt',
             'tests/k4/transport/probe.vt', 'tests/k4/transport/irq.s0', 'tests/k4/transport/shutdown.s0']
    inputs = {}
    for name in names:
        dst = out / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dst)
        inputs[name] = sha(dst)
    if args.no_irq:
        path = out / 'tests/k4/transport/irq.s0'
        text = path.read_text()
        assert text.count('addi x5, x0, 512') == 1
        path.write_text(text.replace('addi x5, x0, 512', 'addi x5, x0, 0'))
    manifest = ['format 1', 'profile suba-kernel', 'entry draft::probe::start',
                'bind panic=draft::probe::panic', 'bind trap_dispatch=draft::block::handle']
    manifest += ['source ' + n for n in names if n.endswith('.vt')]
    manifest += ['assembly ' + n for n in names if n.endswith('.s0')]
    manifest += ['output probe.elf']
    (out / 'probe.build').write_text('\n'.join(manifest) + '\n')
    command = ['qemu-riscv64', '-s', '1048576', str(compiler), 'build', 'probe.build']
    result = subprocess.run(command, cwd=out, capture_output=True, timeout=120)
    (out / 'compile.log').write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    disk = out / 'disk.raw'
    with disk.open('xb') as stream:
        stream.truncate(268435456)
    command = ['qemu-system-riscv64', '-machine', 'virt', '-m', '512M', '-smp', '1',
               '-nographic', '-bios', str(FIRMWARE), '-kernel', str(out / 'probe.elf'),
               '-global', 'virtio-mmio.force-legacy=false', '-drive',
               f'file={disk},if=none,format=raw,id=blk,cache=writeback',
               '-device', 'virtio-blk-device,drive=blk', '-no-reboot']
    evidence = dict(scope='shared transport only; actual S trap IRQ, no full K4 claim',
                    inputs=inputs, compiler_sha256=sha(compiler), firmware_sha256=sha(FIRMWARE),
                    elf_sha256=sha(out / 'probe.elf'), command=command, no_irq=args.no_irq,
                    boots=[], passed=False)
    try:
        for index in range(1 if args.no_irq else 2):
            timed_out = False
            try:
                run = subprocess.run(command, capture_output=True, timeout=4 if args.no_irq else 40)
                log = run.stdout + run.stderr
                code = run.returncode
            except subprocess.TimeoutExpired as error:
                timed_out = True
                log = (error.stdout or b'') + (error.stderr or b'')
                code = None
            (out / f'boot{index}.log').write_bytes(log)
            if args.no_irq:
                assert timed_out and b'K4 draft panic=000000000000006a' in log, log[-600:]
                assert b'K4 transport 16bit index wrap verified' not in log
            else:
                assert code == 0 and not timed_out, log[-600:]
                assert b'K4 transport 16bit index wrap verified' in log
                assert (b'K4 draft initially zero' if index == 0 else b'K4 draft persisted') in log
            evidence['boots'].append(dict(exit=code, timed_out=timed_out,
                                           log_sha256=hashlib.sha256(log).hexdigest()))
        evidence['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('transport IRQ-disabled negative passed' if args.no_irq else
          'transport: two normal boots, FLUSH, 65544 IRQ transfers/boot and u16 wrap passed')


if __name__ == '__main__':
    main()
