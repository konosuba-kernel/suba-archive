#!/usr/bin/env python3
"""Save through the real editor, power off through desktop keys, boot and read."""
import argparse
import json
from pathlib import Path
import select
import time
from k7_gui import start, sha
from read_disk import Disk


def shutdown(gui):
    gui.input.chord('ctrl', 'alt', 'f12')
    deadline = time.monotonic() + 60
    # This harness already owns QMP. Drain guest-origin events on that connection.
    while time.monotonic() < deadline:
        if select.select([gui.qmp.socket], [], [], .1)[0]:
            line = gui.qmp.stream.readline()
            if not line:
                break
            gui.qmp.log.append(json.loads(line))
        serial = (gui.out / 'serial.log').read_text()
        assert 'panic' not in serial.lower(), serial[-3000:]
    assert gui.process.wait(timeout=3) == 0, 'guest shutdown did not exit successfully'
    assert any(e.get('event') == 'SHUTDOWN' and e['data'].get('guest') for e in gui.qmp.log)
    assert 'power: flushed action=0' in (gui.out / 'serial.log').read_text()
    gui.record['guest_shutdown_before_harness_cleanup'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--xvfb', required=True, type=Path)
    args = parser.parse_args()
    system, out = args.system.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = {'passed': False, 'system_report_sha256': sha(system / 'verification.json')}
    original = (system / 'initial/work/hello.vt').read_bytes()
    expected = original.replace(b'return 41;', b'return 42;')
    assert expected != original
    try:
        with start(system, out / 'first', args.xvfb.resolve()) as gui:
            gui.expect('notes-ready', 'notes.txt', 72, 92, (125, 211, 252))
            gui.input.click(50, 150)
            gui.expect('source-focused', 'hello.vt', 48, 68, (125, 211, 252))
            gui.input.click(136, 180)
            gui.input.chord('delete'); gui.input.chord('delete'); gui.input.text('42')
            gui.input.chord('ctrl', 's')
            gui.expect('saved', 'Saved', 48, 88)
            gui.input.chord('ctrl', 'm'); gui.input.text('compiler.build'); gui.input.chord('enter')
            gui.expect('native-manifest', 'compiler.build', 48, 104, (148, 163, 184))
            gui.input.chord('ctrl', 'b')
            gui.expect('native-build-active', 'Building; editing remains available; Esc cancels', 48, 88)
            gui.expect('native-build-frozen', 'compile started', 48, 480, (134, 239, 172), timeout=300)
            gui.input.chord('ctrl', 'alt', 'f11')
            deadline = time.monotonic() + 90
            while 'suba K4: mounted boot=2' not in (gui.out / 'serial.log').read_text():
                assert gui.process.poll() is None and time.monotonic() < deadline, 'desktop cold reboot failed'
                assert 'panic' not in (gui.out / 'serial.log').read_text().lower()
                time.sleep(.05)
            gui.expect('cold-reboot-ready', 'notes.txt', 72, 92, (125, 211, 252))
            assert any(e.get('event') == 'RESET' and e['data'].get('guest') for e in gui.qmp.log)
            shutdown(gui)
            record['first'] = gui.record
        disk = Disk(out / 'first/disk.raw', system / 'abi/contract.vt')
        assert disk.read('/work/hello.vt') == expected
        assert not any(path.startswith('/jobs/') for path in disk.paths)
        assert not any(node['flags'] != 0 for node in disk.nodes.values())
        with start(system, out / 'reboot', args.xvfb.resolve(), disk=out / 'first/disk.raw') as gui:
            gui.expect('new-boot-ready', 'notes.txt', 72, 92, (125, 211, 252))
            gui.input.click(50, 150)
            gui.expect('persisted-text', 'return 42;', 80, 176, (219, 234, 254))
            shutdown(gui)
            record['reboot'] = gui.record
        assert Disk(out / 'reboot/disk.raw', system / 'abi/contract.vt').read('/work/hello.vt') == expected
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K10 real desktop save, guest power off and new-boot read passed')


if __name__ == '__main__':
    main()
