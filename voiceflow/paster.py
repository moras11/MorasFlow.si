"""Paste into the active window, then give the user's clipboard back once the target has actually read the text.

Apps read the clipboard when they get round to handling Ctrl+V, not when it is sent: Windows Terminal has taken
over 1.5 s, and any fixed restore delay made it paste the user's older clipboard instead. So the dictation goes on
the clipboard delay-rendered: a hidden window owns it, and Windows asks that window for the text (WM_RENDERFORMAT)
the moment someone reads it. The user's clipboard comes back only after that read (or after TIMEOUT if nothing
reads, i.e. the paste didn't happen). Background readers (clipboard history, Explorer) are refused the text, so they
can't fake the "read" signal, and dictations are marked to stay out of Win+V history and cloud clipboard.
"""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

import keyboard
import pyperclip

GRACE = 0.5  # after the target's read, before restoring (some apps read twice)
TIMEOUT = 10.0  # nobody read by then: the paste didn't happen, give the user their clipboard back
BACKGROUND_READERS = {"svchost.exe", "explorer.exe"}  # read every clipboard change; never the paste target (unless
#                                                       pasting into Explorer itself, which is allowed)
MASK_VK = 0xE8  # unassigned key: pressed before a Win key-up so it can't open the Start menu
# Modifiers that would turn Ctrl+V into another shortcut (Ctrl+Win+V, Ctrl+Alt+V...), with their keybd_event flags.
MODIFIERS = {"win": (0x5B, 1), "right win": (0x5C, 1), "alt": (0xA4, 0), "right alt": (0xA5, 1),
             "shift": (0xA0, 0), "right shift": (0xA1, 0)}  # name: (virtual key, KEYEVENTF_EXTENDEDKEY)

log = logging.getLogger("voiceflow")
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = LRESULT
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardOwner.restype = wintypes.HWND
user32.GetOpenClipboardWindow.restype = wintypes.HWND
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

CF_UNICODETEXT = 13
WM_RENDERFORMAT, WM_RENDERALLFORMATS, WM_DESTROYCLIPBOARD = 0x0305, 0x0306, 0x0307
WM_OFFER = 0x8001  # WM_APP + 1: "put this text on the clipboard", handled on the clipboard window's thread
HWND_MESSAGE = wintypes.HWND(-3)


def _global(data):
    handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE; the clipboard owns it once set
    ctypes.memmove(kernel32.GlobalLock(handle), data, len(data))
    kernel32.GlobalUnlock(handle)
    return handle


def process_name(pid):
    """Lower-case exe name for a process id, or None."""
    process = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not process:
        return None
    name, size = ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
    ok = kernel32.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size))
    kernel32.CloseHandle(process)
    return name.value.rsplit("\\", 1)[-1].lower() if ok else None


def _reader():
    """Exe of the process reading the clipboard now; None if it opened the clipboard without a window."""
    hwnd = user32.GetOpenClipboardWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return process_name(pid.value)


class DelayedClipboard:
    """Owns the clipboard through a hidden window on its own thread and hands the text over on request."""

    def __init__(self):
        self.text, self.target = "", None
        self.read = threading.Event()  # the paste target asked for our text
        self.replaced = threading.Event()  # someone else (the user) put something new on the clipboard
        self.offered_at = self.read_at = None
        self._setting = False
        self._history_formats = [user32.RegisterClipboardFormatW(name) for name in (
            "ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard")]
        ready = threading.Event()
        threading.Thread(target=self._loop, args=(ready,), daemon=True, name="clipboard").start()
        ready.wait()

    def _loop(self, ready):
        self._proc = WNDPROC(self._wndproc)  # keep a reference: the callback dies with its Python object
        cls = WNDCLASSW(lpfnWndProc=self._proc, hInstance=kernel32.GetModuleHandleW(None),
                        lpszClassName="MorasFlowClipboard")
        user32.RegisterClassW(ctypes.byref(cls))
        self.hwnd = user32.CreateWindowExW(0, cls.lpszClassName, None, 0, 0, 0, 0, 0, HWND_MESSAGE, None,
                                           cls.hInstance, None)
        ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.DispatchMessageW(ctypes.byref(msg))

    def _supply(self):
        user32.SetClipboardData(CF_UNICODETEXT, _global((self.text + "\0").encode("utf-16-le")))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_OFFER:
                return self._take_clipboard(hwnd)
            if msg == WM_RENDERFORMAT:
                if wparam == CF_UNICODETEXT:
                    reader = _reader()
                    if reader in BACKGROUND_READERS and reader != self.target:
                        return 0  # supply nothing; the promise stays for the real target's read
                    self._supply()  # Windows already has the clipboard open for the reader
                    if not self.read.is_set():
                        self.read_at = time.perf_counter()
                        self.read.set()
                return 0
            if msg == WM_RENDERALLFORMATS:  # the window is going away: leave real text behind
                if user32.OpenClipboard(hwnd):
                    if user32.GetClipboardOwner() == hwnd:
                        self._supply()
                    user32.CloseClipboard()
                return 0
            if msg == WM_DESTROYCLIPBOARD:
                if not self._setting:
                    self.replaced.set()
                return 0
        except Exception:
            log.exception("Clipboard window error")
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _take_clipboard(self, hwnd):
        for _ in range(50):  # another app may hold the clipboard for a moment
            if user32.OpenClipboard(hwnd):
                break
            time.sleep(0.01)
        else:
            return 0
        try:
            self._setting = True
            user32.EmptyClipboard()  # tells the previous owner (maybe us): not a user copy, hence _setting
            self._setting = False
            user32.SetClipboardData(CF_UNICODETEXT, None)  # a promise: rendered when someone reads it
            exclude, history, cloud = self._history_formats
            user32.SetClipboardData(exclude, _global(b"\0"))
            user32.SetClipboardData(history, _global((0).to_bytes(4, "little")))
            user32.SetClipboardData(cloud, _global((0).to_bytes(4, "little")))
        finally:
            user32.CloseClipboard()
        return 1

    def offer(self, text, target):
        """Put text on the clipboard (delay-rendered). target: exe of the paste target, allowed to read it."""
        self.text, self.target = text, target
        self.read.clear()
        self.replaced.clear()
        self.read_at, self.offered_at = None, time.perf_counter()
        if not user32.SendMessageW(self.hwnd, WM_OFFER, 0, 0):
            raise RuntimeError("Couldn't open the clipboard (another app is holding it)")


_clipboard = None
_lock = threading.Lock()
_saved = None  # the user's clipboard, waiting to be restored
_generation = 0  # only the newest paste restores


def release_stale_modifiers():
    """Windows Terminal decides between Ctrl+V and e.g. Ctrl+Win+V from its own record of the keyboard, which only
    updates from key events it receives. If the Win key-up from the hotkey went elsewhere, it still thinks Win is
    down and the paste shortcut doesn't match. Send key-ups for anything the active window thinks is held but
    physically isn't. Returns their names. Never raises: it must not cost the user their paste."""
    try:
        target = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        me = kernel32.GetCurrentThreadId()
        user32.PeekMessageW(ctypes.byref(ctypes.create_string_buffer(48)), None, 0, 0, 0)  # give this thread a queue
        state = (ctypes.c_ubyte * 256)()
        if not target or target == me or not user32.AttachThreadInput(me, target, True):
            return []
        try:  # attached, this thread shares the target's keyboard state
            user32.GetKeyboardState(state)
        finally:
            user32.AttachThreadInput(me, target, False)
        stale = [name for name, (vk, _) in MODIFIERS.items()
                 if state[vk] & 0x80 and not user32.GetAsyncKeyState(vk) & 0x8000]
        if stale:
            user32.keybd_event(MASK_VK, 0, 0, 0)
            user32.keybd_event(MASK_VK, 0, 2, 0)
            for name in stale:
                vk, extended = MODIFIERS[name]
                user32.keybd_event(vk, 0, 2 | extended, 0)  # KEYEVENTF_KEYUP
        return stale
    except Exception:
        return []


def paste(text, target=None):
    """Paste text into the active window; the user's clipboard comes back after the target has read it.
    target: the active window's exe name, the only Explorer/clipboard-history-like reader allowed to read.
    Returns the names of stale modifier keys released first (for the log)."""
    # ponytail: text-only save/restore, so a copied image or file is lost. Upgrade: save every
    # clipboard format via win32 OpenClipboard/EnumClipboardFormats if that bites.
    global _clipboard, _saved, _generation
    with _lock:
        if _clipboard is None:
            _clipboard = DelayedClipboard()
        # No restore pending: the clipboard is the user's. Pending but replaced: the user copied something new
        # since our last paste, and that is now what to give back.
        if _saved is None or _clipboard.replaced.is_set():
            _saved = pyperclip.paste()
        _generation += 1
        mine = _generation
        _clipboard.offer(text, (target or "").lower() or None)
        stale = release_stale_modifiers()
        keyboard.send("ctrl+v")
    threading.Thread(target=_restore_after_read, args=(mine,), daemon=True, name="restore").start()
    return stale


def _restore_after_read(generation):
    global _saved
    read = _clipboard.read.wait(TIMEOUT)
    if read:
        time.sleep(GRACE)
    with _lock:
        if generation != _generation:  # a newer paste owns the restore
            return
        if read:
            log.info("Paste read by the target after %d ms", (_clipboard.read_at - _clipboard.offered_at) * 1000)
        elif _clipboard.replaced.is_set():
            log.info("Clipboard replaced by the user before the paste was read")
        else:
            log.warning("Paste not read within %d s: the target ignored Ctrl+V", TIMEOUT)
        if not _clipboard.replaced.is_set():  # if the user copied something meanwhile, keep theirs
            pyperclip.copy(_saved)
        _saved = None
