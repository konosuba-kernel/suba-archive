"""Send XTest input to a mapped, focused QEMU GTK client; never QMP input.

The helper deliberately reports the selected X11 window and checked geometry.
It does not claim physical keyboard coverage or guest readiness by itself.
"""
import ctypes as C
import ctypes.util
import sys
import time

Pointer = C.c_void_p
Window = C.c_ulong
Int = C.c_int


class Attributes(C.Structure):
    _fields_ = [(name, kind) for name, kind in [
        ('x', Int), ('y', Int), ('width', Int), ('height', Int), ('border_width', Int),
        ('depth', Int), ('visual', Pointer), ('root', Window), ('window_class', Int),
        ('bit_gravity', Int), ('win_gravity', Int), ('backing_store', Int),
        ('backing_planes', Window), ('backing_pixel', Window), ('save_under', Int),
        ('colormap', Window), ('map_installed', Int), ('map_state', Int),
        ('all_event_masks', C.c_long), ('your_event_mask', C.c_long),
        ('do_not_propagate_mask', C.c_long), ('override_redirect', Int), ('screen', Pointer)]]


class Input:
    def __init__(self, name, display=None):
        self.x = C.CDLL(ctypes.util.find_library('X11'))
        self.test = C.CDLL(ctypes.util.find_library('Xtst'))
        self.x.XOpenDisplay.argtypes = [C.c_char_p]
        self.x.XOpenDisplay.restype = Pointer
        self.x.XDefaultRootWindow.argtypes = [Pointer]
        self.x.XDefaultRootWindow.restype = Window
        self.x.XQueryTree.argtypes = [Pointer, Window, C.POINTER(Window), C.POINTER(Window),
                                      C.POINTER(C.POINTER(Window)), C.POINTER(C.c_uint)]
        self.x.XFetchName.argtypes = [Pointer, Window, C.POINTER(C.c_char_p)]
        self.x.XFree.argtypes = [Pointer]
        self.x.XGetWindowAttributes.argtypes = [Pointer, Window, C.POINTER(Attributes)]
        self.x.XGetInputFocus.argtypes = [Pointer, C.POINTER(Window), C.POINTER(Int)]
        self.x.XSetInputFocus.argtypes = [Pointer, Window, Int, Window]
        self.x.XFlush.argtypes = [Pointer]
        self.x.XSync.argtypes = [Pointer, Int]
        self.x.XRaiseWindow.argtypes = [Pointer, Window]
        self.x.XCloseDisplay.argtypes = [Pointer]
        self.x.XKeysymToKeycode.argtypes = [Pointer, Window]
        self.x.XKeysymToKeycode.restype = C.c_uint
        self.x.XTranslateCoordinates.argtypes = [Pointer, Window, Window, Int, Int,
                                                 C.POINTER(Int), C.POINTER(Int), C.POINTER(Window)]
        self.test.XTestFakeMotionEvent.argtypes = [Pointer, Int, Int, Int, Window]
        self.test.XTestFakeButtonEvent.argtypes = [Pointer, C.c_uint, Int, Window]
        self.test.XTestFakeKeyEvent.argtypes = [Pointer, C.c_uint, Int, Window]
        self.display = self.x.XOpenDisplay(display.encode() if display else None)
        if not self.display:
            raise RuntimeError('No X11 display')
        self.root = self.x.XDefaultRootWindow(self.display)
        self.name = name
        self.old_focus, self.old_revert = Window(), Int()
        self.x.XGetInputFocus(self.display, C.byref(self.old_focus), C.byref(self.old_revert))
        self.window = self.wait_mapped()
        self.x.XRaiseWindow(self.display, self.window)
        self.x.XSetInputFocus(self.display, self.window, 2, 0)
        self.x.XSync(self.display, False)
        focus, revert = Window(), Int()
        self.x.XGetInputFocus(self.display, C.byref(focus), C.byref(revert))
        if focus.value != self.window:
            raise RuntimeError(('GTK focus not established', focus.value, self.window))
        xx, yy, child = Int(), Int(), Window()
        if not self.x.XTranslateCoordinates(self.display, self.window, self.root, 0, 0,
                                             C.byref(xx), C.byref(yy), C.byref(child)):
            raise RuntimeError('GTK origin unavailable')
        self.origin = (xx.value, yy.value)
        print('GTK/XTest mapped window', hex(self.window), 'origin', self.origin, flush=True)

    def find(self, window, depth=0):
        text = C.c_char_p()
        self.x.XFetchName(self.display, window, C.byref(text))
        name = text.value.decode(errors='replace') if text.value else ''
        if text:
            self.x.XFree(text)
        if self.name in name:
            return window
        if depth >= 8:
            return None
        root, parent = Window(), Window()
        children = C.POINTER(Window)()
        count = C.c_uint()
        if not self.x.XQueryTree(self.display, window, C.byref(root), C.byref(parent),
                                 C.byref(children), C.byref(count)):
            return None
        ids = [children[i] for i in range(count.value)]
        if children:
            self.x.XFree(children)
        for child in ids:
            found = self.find(child, depth + 1)
            if found is not None:
                return found
        return None

    def wait_mapped(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            window = self.find(self.root)
            attrs = Attributes()
            if window is not None and self.x.XGetWindowAttributes(self.display, window, C.byref(attrs)):
                if attrs.map_state == 2 and attrs.width >= 1024 and attrs.height >= 768:
                    return window
            time.sleep(.05)
        raise RuntimeError('GTK client did not become viewable at the requested size')

    def sync(self):
        self.x.XSync(self.display, False)
        time.sleep(.1)

    def move(self, x, y):
        self.test.XTestFakeMotionEvent(self.display, -1, self.origin[0] + x, self.origin[1] + y, 0)
        self.sync()

    def button(self, down, name="left"):
        number = {"left": 1, "right": 3}[name]
        self.test.XTestFakeButtonEvent(self.display, number, down, 0)
        self.sync()

    def key(self, down, name="a"):
        symbol = {"a": ord("a"), "ctrl": 0xffe3, "alt": 0xffe9, "esc": 0xff1b}[name]
        code = self.x.XKeysymToKeycode(self.display, symbol)
        self.test.XTestFakeKeyEvent(self.display, code, down, 0)
        self.sync()

    def close(self):
        self.x.XSetInputFocus(self.display, self.old_focus, self.old_revert.value, 0)
        self.x.XSync(self.display, False)
        self.x.XCloseDisplay(self.display)


def main():
    control = Input(sys.argv[1] if len(sys.argv) > 1 else 'k5-driver')
    try:
        # Initial click gives GTK's guest display widget its own focus as well.
        control.move(400, 350)
        control.button(True)
        control.button(False)
        control.key(True)
        control.key(False)
        control.move(600, 450)
        control.button(True)
        control.button(False)
    finally:
        control.close()


if __name__ == '__main__':
    main()
