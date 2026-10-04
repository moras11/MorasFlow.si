import ctypes
import threading

import keyboard
import pyperclip

# Apps read the clipboard when they get round to handling Ctrl+V, not when it is sent. Windows Terminal sometimes
# takes over 300 ms, and restoring before then made it paste the user's previous clipboard instead.
RESTORE_DELAY = 1.5
MASK_VK = 0xE8  # unassigned key: pressed before a Win key-up so it can't open the Start menu
# Modifiers that would turn Ctrl+V into another shortcut (Ctrl+Win+V, Ctrl+Alt+V...), with their keybd_event flags.
MODIFIERS = {"win": (0x5B, 1), "right win": (0x5C, 1), "alt": (0xA4, 0), "right alt": (0xA5, 1),
             "shift": (0xA0, 0), "right shift": (0xA1, 0)}  # name: (virtual key, KEYEVENTF_EXTENDEDKEY)

_lock = threading.Lock()
_saved = None  # the user's clipboard from before the first paste still waiting to be restored
_generation = 0  # only the newest paste's timer restores


def release_stale_modifiers():
    """Windows Terminal decides between Ctrl+V and e.g. Ctrl+Win+V from its own record of the keyboard, which only
    updates from key events it receives. If the Win key-up from the hotkey went elsewhere, it still thinks Win is
    down and the paste shortcut doesn't match. Send key-ups for anything the active window thinks is held but
    physically isn't. Returns their names. Never raises: it must not cost the user their paste."""
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
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


def paste(text):
    """Paste text into the active window. The user's clipboard comes back later, off this thread.
    Returns the names of stale modifier keys released first (for the log)."""
    # ponytail: text-only save/restore, so a copied image or file is lost. Upgrade: save every
    # clipboard format via win32 OpenClipboard/EnumClipboardFormats if that bites.
    global _saved, _generation
    with _lock:
        if _saved is None:  # with a restore pending, the clipboard holds our last dictation, not the user's
            _saved = pyperclip.paste()
        pyperclip.copy(text)
        _generation += 1
        mine = (_generation, ctypes.windll.user32.GetClipboardSequenceNumber())
        stale = release_stale_modifiers()
        keyboard.send("ctrl+v")
    timer = threading.Timer(RESTORE_DELAY, _restore, mine)
    timer.daemon = True
    timer.start()
    return stale


def _restore(generation, sequence):
    global _saved
    with _lock:
        if generation != _generation:  # a newer paste will restore instead
            return
        # The sequence number changes on every write (not on reads): if it moved, the user copied something new.
        if ctypes.windll.user32.GetClipboardSequenceNumber() == sequence:
            pyperclip.copy(_saved)
        _saved = None
