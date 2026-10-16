#!/usr/bin/env python3
"""Select native build manifests through the production editor keyboard UI."""
import argparse
import json
from pathlib import Path
from k7_gui import start, sha
from read_disk import Disk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--xvfb', type=Path, required=True)
    args = parser.parse_args()
    system, out = args.system.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = {'passed': False, 'system': str(system), 'system_report_sha256': sha(system / 'verification.json')}
    try:
        with start(system, out / 'first', args.xvfb.resolve()) as gui:
            key = gui.input
            gui.expect('notes-ready', 'notes.txt', 72, 92, (125, 211, 252))
            key.click(50, 150)
            gui.expect('source-ready', 'hello.vt', 48, 68, (125, 211, 252))
            def choose(name):
                key.chord('ctrl', 'm'); key.text(name); key.chord('enter')
                gui.expect('selected-' + name, 'Manifest selected; Ctrl+B builds saved sources', 48, 88)
                gui.expect('manifest-label-' + name, name, 48, 104, (148, 163, 184))
            choose('compiler.build')
            choose('kernel.build')
            key.chord('ctrl', 'r')
            gui.expect('kernel-not-app', 'Kernel ELF is a saved artifact; cannot run as an app', 48, 88)
            key.chord('ctrl', 'm'); key.text('missing.build'); key.chord('enter')
            gui.expect('missing-rejected', 'Cannot read build manifest', 48, 88)
            key.chord('esc')
            gui.expect('selection-retained', 'kernel.build', 48, 104, (148, 163, 184))
            choose('program.build')
            key.chord('ctrl', 'b')
            gui.expect('build-start', 'Building; editing remains available; Esc cancels', 48, 88)
            key.chord('ctrl', 'm')
            gui.expect('active-build-identity', 'Wait for build completion before changing manifest', 48, 88)
            gui.expect('build-complete', 'Build complete; Ctrl+R runs output', 48, 88, timeout=300)
            key.chord('ctrl', 'r')
            gui.expect('run-complete', 'Program exited; status in log', 48, 88)
            gui.expect('exit41', 'program exit=41 cause=0', 48, 480, (134, 239, 172))
            key.chord('ctrl', 's'); gui.expect('synced', 'Saved', 48, 88)
            record['gui'] = gui.record
        disk = Disk(out / 'first/disk.raw', system / 'abi/contract.vt')
        assert disk.read('/work/hello.vt') == (system / 'initial/work/hello.vt').read_bytes()
        assert disk.read('/work/compiler.build') == (system / 'initial/work/compiler.build').read_bytes()
        assert disk.read('/work/kernel.build') == (system / 'initial/work/kernel.build').read_bytes()
        assert disk.read('/work/hello.elf').startswith(b'\x7fELF')
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K9 editor manifest selection and normal program build/run passed')


if __name__ == '__main__':
    main()
