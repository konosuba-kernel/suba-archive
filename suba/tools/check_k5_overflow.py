#!/usr/bin/env python3
"""Actual input IRQ overflow: defer only event consumption, replenish device DMA.

Each host input frame fits the 64-descriptor device queue. This tests observable
software overflow, not QEMU's documented invisible oversized-frame drop.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
from check_k5_devices import FILES, ROOT, FIRMWARE, Qmp, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    compiler, out = args.compiler.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = {'passed': False, 'scope': 'bare S input software overflow over actual IRQ',
              'compiler_sha256': sha(compiler), 'inputs': {}}
    for name in FILES:
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        record['inputs'][name] = sha(target)
    platform = out / 'platform/devices.vt'
    text = platform.read_text()
    assert text.count('0x40000000') == 1
    platform.write_text(text.replace('0x40000000', '0x00000000'))
    probe = out / 'tests/k5/device_probe.vt'
    text = probe.read_text()
    anchor = '        loop {\n            k5_poll_irq();\n            match input::next() {'
    assert text.count(anchor) == 1
    inserted = '''        let consume_at: usize = io::time() + 50000000_usize;
        while io::time() < consume_at { k5_poll_irq(); }
        machine::text("K5 HOLD ENDED resets=");
        number(input::software_resets()); machine::text("\\n");
'''
    probe.write_text(text.replace(anchor, inserted + anchor))
    manifest = ['format 1', 'profile suba-kernel', 'entry test::k5_device::start',
                'bind panic=test::k5_device::panic', 'bind trap_dispatch=test::k5_device::handle']
    manifest += ['source ' + name for name in FILES if name.endswith('.vt')]
    manifest += ['assembly ' + name for name in FILES if name.endswith('.s0')]
    manifest += ['output probe.elf']
    (out / 'probe.build').write_text('\n'.join(manifest) + '\n')
    record['test_inputs'] = {name: sha(out / name) for name in FILES}
    process, qmp = None, None
    try:
        result = subprocess.run(['qemu-riscv64', '-s', '1048576', str(compiler), 'build', 'probe.build'],
                                cwd=out, capture_output=True, timeout=120)
        (out / 'compile.log').write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        record['elf_sha256'] = sha(out / 'probe.elf')
        command = ['qemu-system-riscv64', '-machine', 'virt', '-m', '512M', '-smp', '1',
                   '-bios', str(FIRMWARE), '-kernel', str(out / 'probe.elf'), '-device', 'ramfb',
                   '-device', 'virtio-keyboard-device', '-device', 'virtio-tablet-device',
                   '-global', 'virtio-mmio.force-legacy=false', '-display', 'none',
                   '-serial', 'file:' + str(out / 'serial.log'), '-monitor', 'none',
                   '-qmp', 'unix:' + str(out / 'qmp.sock') + ',server=on,wait=off']
        record['command'] = command
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if (out / 'serial.log').exists() and 'K5 DEVICE READY' in (out / 'serial.log').read_text():
                break
            assert process.poll() is None
            time.sleep(.02)
        else:
            raise AssertionError('driver did not become ready')
        qmp = Qmp(out / 'qmp.sock')
        qmp.input([{'type': 'btn', 'data': {'down': True, 'button': 'left'}}])
        # 100 one-edge + SYN_REPORT frames, separated to let actual IRQs drain.
        for i in range(100):
            qmp.call('input-send-event', {'events': [
                {'type': 'key', 'data': {'down': i % 2 == 0, 'key': {'type': 'qcode', 'data': 'a'}}}]})
            time.sleep(.01)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            log = (out / 'serial.log').read_text()
            if 'K5 HOLD ENDED' in log:
                break
            assert process.poll() is None
            time.sleep(.05)
        else:
            raise AssertionError('hold did not finish')
        qmp.input([{'type': 'abs', 'data': {'axis': 'x', 'value': 16000}},
                   {'type': 'abs', 'data': {'axis': 'y', 'value': 16000}}])
        for down in [False, True, False]:
            qmp.input([{'type': 'btn', 'data': {'down': down, 'button': 'left'}}])
        for down in [True, False]:
            qmp.input([{'type': 'key', 'data': {'down': down, 'key': {'type': 'qcode', 'data': 'a'}}}])
        log = (out / 'serial.log').read_text()
        assert 'PANIC' not in log
        resets = [int(line.split('=')[1].strip(), 16) for line in log.splitlines() if line.startswith('K5 HOLD ENDED')]
        assert len(resets) == 1 and resets[0] >= 1, resets
        events = [[int(word, 16) for word in line.split()[1:]] for line in log.splitlines() if line.startswith('EVENT ')]
        assert events[0][0] == 5, events[:3]
        assert any(event[0] == 2 and event[3] == 0 for event in events)
        assert [event[2] for event in events if event[0:2] == [1, 30]][-2:] == [1, 0]
        assert max(event[4] for event in events) >= 100
        record.update(passed=True, resets=resets[0], events=events)
    finally:
        if qmp is not None:
            (out / 'qmp.json').write_text(json.dumps(qmp.log, indent=2) + '\n')
        if process is not None:
            process.terminate()
            _, stderr = process.communicate(timeout=5)
            (out / 'stderr.log').write_bytes(stderr)
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Actual IRQ software overflow/reset and fresh edges passed')


if __name__ == '__main__':
    main()
