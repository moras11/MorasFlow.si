import time

import keyboard
import pyperclip

RESTORE_DELAY = 0.3  # give the target app time to read the clipboard before restoring it


def paste(text):
    """Paste text into the active window, then put the user's clipboard back."""
    # ponytail: text-only save/restore, so a copied image or file is lost. Upgrade: save every
    # clipboard format via win32 OpenClipboard/EnumClipboardFormats if that bites.
    saved = pyperclip.paste()
    pyperclip.copy(text)
    keyboard.send("ctrl+v")
    time.sleep(RESTORE_DELAY)
    pyperclip.copy(saved)
