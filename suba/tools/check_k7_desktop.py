#!/usr/bin/env python3
"""Exercise the production editing/building UI through real GTK input.

Guest persistence is observed only after sync and stopping QEMU. Reboot uses the
same disk bytes. Host-built oracle is separate and is never installed in guest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import time
from k7_gui import start, sha
from read_disk import Disk

YELLOW = (251, 191, 36)
CYAN = (125, 211, 252)
GREEN = (134, 239, 172)
TEXT = (219, 234, 254)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--xvfb', type=Path, required=True)
    args = parser.parse_args()
    system, out = args.system.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = {'passed': False, 'system': str(system), 'stages': [], 'latencies': [],
              'scope': 'functional GTK closed loop, not K10 100ms/dual-compiler target'}
    record['test_inputs'] = {}
    root = Path(__file__).resolve().parents[1]
    for name in ['tools/check_k7_desktop.py', 'tools/k7_gui.py', 'tools/read_disk.py',
                 'tools/mkfs.py', 'tools/check_k5_devices.py', 'tests/k5/gtk_input.py']:
        target = out / 'harness' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
        record['test_inputs'][name] = sha(target)
    first = out / 'first'
    try:
        with start(system, first, args.xvfb.resolve()) as gui:
            key = gui.input
            def expect(name, text, x=48, y=88, color=YELLOW):
                result = gui.expect(name, text, x, y, color, timeout=180)
                record['stages'].append(result)
            def source():
                key.click(50, 150)
                expect('source-focused-' + str(len(record['stages'])), 'hello.vt', 48, 68, CYAN)
            expect('notes-ready', 'notes.txt', 72, 92, CYAN)
            expect('chinese', '你好，suba。', 72, 144, TEXT)
            source()
            began = time.monotonic()
            key.chord('ctrl', 'b')
            expect('first-build', 'Build complete; Ctrl+R runs output')
            record['latencies'].append({'name': 'first-build', 'seconds': time.monotonic() - began})
            key.chord('ctrl', 'r')
            expect('run-first', 'Program exited; status in log')
            expect('exit-41', 'program exit=41 cause=0', 48, 480, GREEN)
            # Change a real source token through the ordinary editor.
            key.click(136, 180)
            key.chord('delete'); key.chord('delete'); key.text('42')
            key.chord('ctrl', 'b')
            expect('second-started', 'Building; editing remains available; Esc cancels')
            # Prove snapshot freeze happened before saving the other document.
            expect('compiler-started', 'compile started', 48, 480, GREEN)
            began = time.monotonic()
            key.click(690, 180)
            expect('other-window-focused', 'notes.txt', 72, 92, CYAN)
            key.text('x'); key.chord('ctrl', 's')
            expect('other-window-saved', 'Saved', 72, 112)
            record['latencies'].append({'name': 'other-window-edit-save', 'seconds': time.monotonic() - began})
            source()
            expect('second-build', 'Build complete; Ctrl+R runs output')
            key.chord('ctrl', 'r')
            expect('run-second', 'Program exited; status in log')
            expect('exit-42', 'program exit=42 cause=0', 48, 480, GREEN)
            # Failed compile retains the published program; diagnostic maps exact
            # frozen bytes, then rejects the same offset after an unsaved edit.
            key.click(136, 180); key.chord('delete'); key.text('x'); key.chord('ctrl', 'b')
            expect('invalid-source', 'Build failed; Ctrl+J jumps to a current diagnostic')
            key.chord('ctrl', 'j')
            expect('fresh-diagnostic', 'Diagnostic source matches frozen input')
            key.text('y'); key.chord('ctrl', 'j')
            expect('stale-diagnostic', 'Stale diagnostic: source has changed; rebuild')
            key.click(660, 50)
            expect('dirty-close', 'Unsaved changes: Ctrl-S then close; Ctrl-Alt-Esc discards')
            key.click(136, 180); key.chord('delete'); key.chord('delete'); key.text('4')
            key.chord('ctrl', 's'); expect('repaired-source', 'Saved')
            key.chord('ctrl', 'b')
            expect('cancel-start', 'Building; editing remains available; Esc cancels')
            key.chord('esc')
            expect('cancelled', 'Build cancelled; committed publications remain valid')
            # Save calls sync_all after atomic replace, after Job collection too.
            key.chord('ctrl', 's'); expect('final-sync', 'Saved')
        disk = Disk(first / 'disk.raw', system / 'abi/contract.vt')
        expected_source = (system / 'initial/work/hello.vt').read_bytes().replace(b'return 41;', b'return 42;')
        assert disk.read('/work/hello.vt') == expected_source
        notes = disk.read('/work/notes.txt')
        assert notes == (system / 'initial/work/notes.txt').read_bytes().replace('保存。'.encode(), '保存。x'.encode())
        assert not [path for path in disk.paths if path.startswith('/jobs/')]
        assert not [path for path in disk.paths if '.suba-save-' in path or path.endswith('.tmp')]
        artifact = disk.read('/work/hello.elf')
        # Same compiler/input host oracle is an independent byte comparison only.
        oracle = out / 'oracle'; oracle.mkdir()
        for name in ('program.build', 'syscall.s0'):
            (oracle / name).write_bytes((system / 'initial/work' / name).read_bytes())
        (oracle / 'hello.vt').write_bytes(expected_source)
        command = ['qemu-riscv64', '-s', '1048576', str(args.compiler.resolve()), 'build', 'program.build']
        result = subprocess.run(command, cwd=oracle, capture_output=True, timeout=60)
        (oracle / 'compile.log').write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0 and (oracle / 'hello.elf').read_bytes() == artifact
        record['persistence'] = {'source_sha256': hashlib.sha256(expected_source).hexdigest(),
                                 'elf_sha256': hashlib.sha256(artifact).hexdigest(),
                                 'bytes': len(artifact), 'host_oracle_equal': True, 'jobs': []}
        with start(system, out / 'reboot', args.xvfb.resolve(), disk=first / 'disk.raw') as gui:
            gui.expect('reboot-notes', 'notes.txt', 72, 92, CYAN)
            gui.input.click(50, 150)
            gui.expect('reboot-source', 'hello.vt', 48, 68, CYAN)
            gui.input.chord('ctrl', 'r')
            gui.expect('reboot-run', 'Program exited; status in log', 48, 88)
            # New process has only this single log line.
            gui.expect('reboot-exit-42', 'program exit=42 cause=0', 48, 416, GREEN)
            record['reboot'] = gui.record
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    print('K7 GTK editing/building/diagnostics/cancel/persistence passed')


if __name__ == '__main__':
    main()
