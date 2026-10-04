import os

import pyperclip
import pystray
from PIL import Image, ImageDraw, ImageOps

import history

APP_NAME = "MorasFlow.si"
COLOURS = {"idle": "#6b7280", "recording": "#dc2626", "processing": "#f59e0b"}  # grey, red, amber
RECENT = 10  # dictations listed under "Copy recent dictation"


def preview(text, width=60):
    """One menu line: whitespace collapsed, shortened, and & doubled (Windows menus treat & as a shortcut key)."""
    text = " ".join(text.split())
    text = text if len(text) <= width else text[:width - 3].rstrip() + "..."
    return text.replace("&", "&&")


def logo(path, ring=None, size=256):
    """The logo image (config.yaml `logo`) cut to a circle. In the tray a coloured ring shows the state."""
    image = ImageOps.fit(Image.open(path).convert("RGBA"), (256, 256), Image.LANCZOS)  # centre-crops non-squares
    mask = Image.new("L", (256, 256), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 255, 255), fill=255)
    image.putalpha(mask)
    if ring:
        ImageDraw.Draw(image).ellipse((0, 0, 255, 255), outline=ring, width=30)  # ~2 px even at 16 px
    return image if size == 256 else image.resize((size, size), Image.LANCZOS)


class Tray:
    """Tray icon and menu. Reads and writes the shared `state` (mode, cleanup, paused)."""

    def __init__(self, state, modes, folder, history_path, on_pause, logo_path):
        self._images = {name: logo(logo_path, colour, 64) for name, colour in COLOURS.items()}

        def set_mode(icon, item):
            state.mode = item.text

        def toggle_cleanup():
            state.cleanup = not state.cleanup

        def toggle_pause():
            state.paused = not state.paused
            on_pause(state.paused)

        item = pystray.MenuItem

        def recent():
            """Rebuilt by refresh() after each dictation: newest first, click to copy."""
            entries = history.read(history_path)[-RECENT:][::-1]
            # A factory, not a default argument: pystray passes the icon to callbacks that take one.
            copier = lambda text: lambda: pyperclip.copy(text)
            return [item(preview(e["cleaned"]), copier(e["cleaned"])) for e in entries] or \
                [item("No dictations yet", None, enabled=False)]

        menu = pystray.Menu(
            *[item(m, set_mode, checked=lambda i: state.mode == i.text, radio=True) for m in modes],
            pystray.Menu.SEPARATOR,
            item("Cleanup", toggle_cleanup, checked=lambda _: state.cleanup),
            item("Pause listening", toggle_pause, checked=lambda _: state.paused),
            pystray.Menu.SEPARATOR,
            item("Copy recent dictation", pystray.Menu(recent)),
            item("Open history", lambda: history.open_page(history_path)),
            item("Open config folder", lambda: os.startfile(folder)),
            pystray.Menu.SEPARATOR,
            item("Quit", lambda icon: icon.stop()),
        )
        self.icon = pystray.Icon(APP_NAME, self._images["idle"], APP_NAME, menu)

    def set_state(self, name):
        self.icon.icon = self._images[name]

    def refresh(self):
        self.icon.update_menu()  # Windows builds the menu ahead of time; this re-reads recent dictations

    def notify(self, message):
        self.icon.notify(message, APP_NAME)

    def run(self, on_ready):
        """Blocks until Quit. on_ready runs on another thread once the icon is showing."""
        def setup(icon):
            icon.visible = True
            on_ready()
        self.icon.run(setup)
