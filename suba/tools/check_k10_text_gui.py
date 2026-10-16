#!/usr/bin/env python3
"""Real GTK UTF-8 scalar edits, fallback glyphs, failed opens and reboot bytes."""
import argparse
import json
from pathlib import Path
import shutil
import time
from k7_gui import start, sha
from mkfs import format_disk
from read_disk import Disk

TEXT = (219, 234, 254)
CYAN = (125, 211, 252)
BOX = bytes([0,0,127,254] + [64,2] * 12 + [127,254,0,0])


def matches(gui, frame, text, x, y):
    for char in text:
        scalar = ord(char)
        width = gui.font[16 + scalar] if scalar < 65536 else 0
        bitmap = gui.font[16 + 65536 + scalar * 32:16 + 65536 + (scalar + 1) * 32] if width else BOX
        width = width or 16
        for row in range(16):
            for col in range(width):
                bit = bool(bitmap[row * 2 + col // 8] & (128 >> (col % 8)))
                if (frame.getpixel((x + col, y + row)) == TEXT) != bit:
                    return False
        x += width
    return True


def expect_body(gui, name, text):
    began = time.monotonic()
    while time.monotonic() - began < 240:
        frame = gui.frame(name)
        if matches(gui, frame, text, 72, 144):
            item = {'name': name, 'text': text, 'elapsed': time.monotonic() - began,
                    'frame_sha256': sha(gui.out / (name + '.png'))}
            gui.record['stages'].append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
            return
        time.sleep(.25)
    raise AssertionError('UTF-8 body rendering timeout: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--xvfb', type=Path, required=True)
    args = parser.parse_args()
    system, out = args.system.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    tree = out / 'initial'
    shutil.copytree(system / 'initial', tree)
    original = 'A中🙂e\u0301文Z\n'
    expected = 'AX🙂e文Z\n'
    (tree / 'work/mixed.txt').write_text(original)
    (tree / 'work/bad.txt').write_bytes(b'valid prefix\xffinvalid')
    (tree / 'work/large.txt').write_bytes(b'x' * (4 * 1024 * 1024 + 1))
    record = {'passed': False, 'system': str(system), 'system_report_sha256': sha(system / 'verification.json')}
    record['initial_disk'] = format_disk(tree, out / 'input.raw', system / 'abi/contract.vt')
    try:
        with start(system, out / 'first', args.xvfb.resolve(), disk=out / 'input.raw') as gui:
            key = gui.input
            gui.expect('notes-ready', 'notes.txt', 72, 92, CYAN)
            key.click(690, 180)
            key.chord('ctrl', 'o'); key.text('mixed.txt'); key.chord('enter')
            gui.expect('mixed-opened', 'Opened', 72, 112)
            expect_body(gui, 'mixed-glyphs', original.strip())
            # Scalar selection: delete the combining mark, not its base e.
            key.chord('home')
            for _ in range(5): key.chord('right')
            key.chord('shift', 'left'); key.chord('delete')
            expect_body(gui, 'combining-scalar-deleted', 'A中🙂e文Z')
            key.chord('home'); key.chord('right')
            key.chord('shift', 'right'); key.chord('delete'); key.text('X')
            key.chord('ctrl', 's')
            gui.expect('mixed-saved', 'Saved', 72, 112)
            expect_body(gui, 'edited-mixed', expected.strip())
            for name in ('bad.txt', 'large.txt'):
                key.chord('ctrl', 'o')
                gui.expect(name + '-prompt', 'Enter a path relative to /work, then Return', 72, 112)
                key.text(name); key.chord('enter')
                gui.expect(name + '-rejected', 'Open failed; check path and UTF-8', 72, 112, timeout=300)
                key.chord('esc')
                gui.expect(name + '-cancel-ack', 'Open cancelled', 72, 112)
                gui.expect(name + '-old-document', 'mixed.txt', 72, 92, CYAN)
                expect_body(gui, name + '-bytes-retained', expected.strip())
            key.chord('ctrl', 's'); gui.expect('final-sync', 'Saved', 72, 112)
            record['first'] = gui.record
        disk = Disk(out / 'first/disk.raw', system / 'abi/contract.vt')
        assert disk.read('/work/mixed.txt') == expected.encode()
        assert disk.read('/work/bad.txt') == (tree / 'work/bad.txt').read_bytes()
        assert disk.read('/work/large.txt') == (tree / 'work/large.txt').read_bytes()
        with start(system, out / 'reboot', args.xvfb.resolve(), disk=out / 'first/disk.raw') as gui:
            gui.expect('reboot-ready', 'notes.txt', 72, 92, CYAN)
            gui.input.click(690, 180)
            gui.input.chord('ctrl', 'o'); gui.input.text('mixed.txt'); gui.input.chord('enter')
            gui.expect('reboot-opened', 'Opened', 72, 112)
            expect_body(gui, 'reboot-mixed-glyphs', expected.strip())
            record['reboot'] = gui.record
        record['full_byte_equal'] = True
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    print('K10 UTF-8 GUI edits, failed opens and same-disk reboot passed')


if __name__ == '__main__':
    main()
