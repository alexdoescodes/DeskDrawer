import ctypes, ctypes.util, sys, time

x11 = ctypes.CDLL(ctypes.util.find_library("X11"))
xtst = ctypes.CDLL(ctypes.util.find_library("Xtst"))

x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
x11.XFlush.argtypes = [ctypes.c_void_p]
xtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
x11.XStringToKeysym.restype = ctypes.c_ulong
x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
x11.XKeysymToKeycode.restype = ctypes.c_ubyte
x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]

dpy = x11.XOpenDisplay(b":1")
if not dpy:
    sys.exit("no display :1")

def motion(x, y):
    xtst.XTestFakeMotionEvent(dpy, -1, int(x), int(y), 0)
    x11.XFlush(dpy)

def click(button, hold=0.03):
    xtst.XTestFakeButtonEvent(dpy, button, 1, 0)
    x11.XFlush(dpy)
    time.sleep(hold)
    xtst.XTestFakeButtonEvent(dpy, button, 0, 0)
    x11.XFlush(dpy)

def key(name, down):
    code = x11.XKeysymToKeycode(dpy, x11.XStringToKeysym(name.encode()))
    xtst.XTestFakeKeyEvent(dpy, code, 1 if down else 0, 0)
    x11.XFlush(dpy)

cmd, x, y = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
modifier = sys.argv[4] if len(sys.argv) > 4 else None
motion(x, y)
time.sleep(0.3)

if modifier:
    key(modifier, True)
    time.sleep(0.1)

if cmd == "double":
    click(1); time.sleep(0.08); click(1)
elif cmd == "single":
    click(1)
elif cmd == "right":
    click(3)
elif cmd == "middle":
    click(2)
if modifier:
    time.sleep(0.1)
    key(modifier, False)

x11.XFlush(dpy)
time.sleep(0.5)
print("sent", cmd, "at", x, y, "modifier", modifier)
