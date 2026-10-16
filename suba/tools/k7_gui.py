"""K7 GTK observation harness: XTest input and framebuffer reads only.

No host guest-memory writes or runtime filesystem service. A private disk copy
isolates each run; screen text is matched against the shipped bitmap font.
"""
from contextlib import contextmanager
import ctypes as C
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from PIL import Image
from check_k5_devices import Qmp, x11_server, sha

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('k5_gtk', ROOT / 'tests/k5/gtk_input.py')
gtk_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gtk_module)


class Input(gtk_module.Input):
    def __init__(self, name, display=None):
        self.events = []
        super().__init__(name, display)

    def move(self, x, y):
        self.events.append({'time': time.monotonic(), 'move': [x, y]})
        super().move(x, y)

    def button(self, down, name='left'):
        self.events.append({'time': time.monotonic(), 'button': name, 'down': down})
        super().button(down, name)

    def key(self, down, name='a'):
        self.events.append({'time': time.monotonic(), 'key': name, 'down': down})
        symbols = {'ctrl': 0xffe3, 'alt': 0xffe9, 'shift': 0xffe1, 'esc': 0xff1b,
                   'enter': 0xff0d, 'backspace': 0xff08, 'delete': 0xffff,
                   'home': 0xff50, 'end': 0xff57, 'left': 0xff51, 'right': 0xff53,
                   'up': 0xff52, 'down': 0xff54, 'tab': 0xff09}
        symbol = ord(name) if len(name) == 1 else symbols[name]
        code = self.x.XKeysymToKeycode(self.display, symbol)
        assert code, ('unmapped key', name)
        self.test.XTestFakeKeyEvent(self.display, code, down, 0)
        self.sync()

    def chord(self, *keys):
        for key in keys:
            self.key(True, key)
        for key in reversed(keys):
            self.key(False, key)

    def text(self, text):
        shift = dict(zip('!@#$%^&*()_+{}|:"<>?~', '1234567890-=[]\\;\',./`'))
        for char in text:
            if char == '\n':
                self.chord('enter')
            elif char == '\t':
                self.chord('tab')
            elif char in shift:
                self.chord('shift', shift[char])
            elif char.isupper() and char.isascii():
                self.chord('shift', char.lower())
            else:
                assert char.isascii(), 'Input methods are not implemented'
                self.chord(char)

    def click(self, x, y):
        self.move(x + 1, y + 1)
        self.button(True)
        self.button(False)


class Gui:
    def __init__(self, snapshot, out, command, process):
        self.snapshot, self.out, self.command, self.process = snapshot, out, command, process
        self.qmp = Qmp(out / 'qmp.sock')
        self.input = None
        self.font = (snapshot / 'initial/sys/suba-bmp.fnt').read_bytes()
        self.record = {'command': command, 'stages': [], 'input': 'GTK/XTest/private-X11',
                       'kernel_sha256': sha(snapshot / 'build/kernel.elf')}
        self.counter = 0

    def frame(self, name='frame'):
        assert self.process.poll() is None, 'QEMU exited'
        serial = self.out / 'serial.log'
        assert not serial.exists() or 'panic' not in serial.read_text().lower(), serial.read_text()
        path = self.out / (name + '.ppm')
        self.qmp.call('screendump', {'filename': str(path)})
        frame = Image.open(path).convert('RGB')
        frame.save(self.out / (name + '.png'))
        return frame

    def text_matches(self, frame, text, x, y, color):
        color = tuple(color)
        for char in text:
            index = ord(char)
            width = self.font[16 + index]
            assert width in (8, 16)
            start = 16 + 65536 + index * 32
            for row in range(16):
                for col in range(width):
                    bit = self.font[start + row * 2 + col // 8] & (128 >> (col % 8))
                    # Background may include a cursor or selection. Foreground
                    # shape must match exactly; no OCR confidence threshold.
                    if (frame.getpixel((x + col, y + row)) == color) != bool(bit):
                        return False
            x += width
        return True

    def expect(self, name, text, x, y, color=(251, 191, 36), timeout=180):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            frame = self.frame(name)
            if self.text_matches(frame, text, x, y, color):
                stage = dict(name=name, text=text, x=x, y=y, elapsed=time.monotonic() - start,
                             frame_sha256=sha(self.out / (name + '.png')))
                self.record['stages'].append(stage)
                print(json.dumps(stage, ensure_ascii=False), flush=True)
                return stage
            time.sleep(.25)
        raise AssertionError('screen text timed out: ' + name)


@contextmanager
def start(snapshot, out, xvfb, disk=None):
    out.mkdir(parents=True, exist_ok=False)
    identity = json.loads((snapshot / 'verification.json').read_text())
    assert identity['built'] and sha(snapshot / 'build/kernel.elf') == identity['kernel']['sha256']
    assert sha(snapshot / 'build/user0.elf') == identity['users'][0]['sha256']
    for name, product in identity['programs'].items():
        assert sha(snapshot / 'initial/sys' / (name + '.elf')) == product['sha256']
    font = next(item for item in identity['initial_disk']['files'] if item['path'] == '/sys/suba-bmp.fnt')
    assert sha(snapshot / 'initial/sys/suba-bmp.fnt') == font['sha256']
    persistent = Path(identity.get('persistent_disk', snapshot / 'disk.raw'))
    shutil.copyfile(disk or persistent, out / 'disk.raw')
    command = json.loads((snapshot / 'run.json').read_text())
    command = [item.replace(str(persistent), str(out / 'disk.raw')) for item in command]
    command[command.index('-serial') + 1] = 'file:' + str(out / 'serial.log')
    command[command.index('-display') + 1] = 'gtk,show-menubar=off,show-tabs=off,zoom-to-fit=off'
    command += ['-name', 'k7-desktop', '-qmp', 'unix:' + str(out / 'qmp.sock') + ',server=on,wait=off']
    with x11_server(xvfb, out) as display:
        environment = dict(os.environ, DISPLAY=display, GDK_BACKEND='x11')
        environment.pop('WAYLAND_DISPLAY', None)
        process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        gui = None
        try:
            deadline = time.monotonic() + 30
            while not (out / 'qmp.sock').exists():
                assert process.poll() is None and time.monotonic() < deadline, 'QEMU startup failed'
                time.sleep(.05)
            gui = Gui(snapshot, out, command, process)
            gui.record['xvfb_sha256'] = sha(xvfb)
            gui.record['initial_disk_sha256'] = sha(out / 'disk.raw')
            try:
                gui.input = Input('k7-desktop', display)
            except RuntimeError:
                serial = out / 'serial.log'
                if serial.exists() and 'panic' in serial.read_text().lower():
                    raise AssertionError('Guest panicked before GTK became ready:\n' + serial.read_text()) from None
                raise
            yield gui
        finally:
            if gui:
                (out / 'observations.json').write_text(json.dumps(gui.record, indent=2) + '\n')
                (out / 'qmp.json').write_text(json.dumps(gui.qmp.log, indent=2) + '\n')
                if gui.input:
                    (out / 'input.json').write_text(json.dumps(gui.input.events, indent=2) + '\n')
                    gui.input.close()
            process.terminate()
            _, error = process.communicate(timeout=10)
            (out / 'stderr.log').write_bytes(error)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--xvfb', type=Path, required=True)
    args = parser.parse_args()
    with start(args.snapshot.resolve(), args.out.resolve(), args.xvfb.resolve()) as gui:
        # JSON commands support exploratory UI runs without host state injection.
        for line in __import__('sys').stdin:
            command = json.loads(line)
            operation = command.pop('op')
            if operation == 'quit':
                break
            if operation == 'frame':
                gui.frame(**command)
                result = 'frame saved'
            elif operation == 'expect':
                result = gui.expect(**command)
            else:
                getattr(gui.input, operation)(*command['args'])
                result = 'input sent'
            print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
