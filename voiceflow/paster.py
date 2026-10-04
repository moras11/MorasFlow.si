import ctypes
import threading

import keyboard
import pyperclip

# Apps read the clipboard when they get round to handling Ctrl+V, not when it is sent. Windows Terminal sometimes
# takes over 300 ms, and restoring before then made it paste the user's previous clipboard instead.
RESTORE_DELAY = 1.5

_lock = threading.Lock()
_saved = None  # the user's clipboard from before the first paste still waiting to be restored
_generation = 0  # only the newest paste's timer restores


def paste(text):
    """Paste text into the active window. The user's clipboard comes back later, off this thread."""
    # ponytail: text-only save/restore, so a copied image or file is lost. Upgrade: save every
    # clipboard format via win32 OpenClipboard/EnumClipboardFormats if that bites.
    global _saved, _generation
    with _lock:
        if _saved is None:  # with a restore pending, the clipboard holds our last dictation, not the user's
            _saved = pyperclip.paste()
        pyperclip.copy(text)
        _generation += 1
        mine = (_generation, ctypes.windll.user32.GetClipboardSequenceNumber())
        keyboard.send("ctrl+v")
    timer = threading.Timer(RESTORE_DELAY, _restore, mine)
    timer.daemon = True
    timer.start()


def _restore(generation, sequence):
    global _saved
    with _lock:
        if generation != _generation:  # a newer paste will restore instead
            return
        # The sequence number changes on every write (not on reads): if it moved, the user copied something new.
        if ctypes.windll.user32.GetClipboardSequenceNumber() == sequence:
            pyperclip.copy(_saved)
        _saved = None
