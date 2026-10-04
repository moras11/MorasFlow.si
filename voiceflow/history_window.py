"""Live history window: every dictation, newest first, searchable, one click to copy.

Started by the tray's "Open history" as its own process, so Tk never shares a thread with the tray or slows dictation.
Usage: history_window.py <history.jsonl> <logo image>
"""
import ctypes
import sys
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import font, ttk

import pyperclip
from PIL import ImageTk

import history
from tray import HISTORY_TITLE, logo


def when(timestamp):
    """("Today" / "Yesterday" / "Sat 04 Oct 2026", "14:05")"""
    d = datetime.fromisoformat(timestamp)
    days = (date.today() - d.date()).days
    return ("Today" if days == 0 else "Yesterday" if days == 1 else d.strftime("%a %d %b %Y")), d.strftime("%H:%M")


class HistoryWindow:
    def __init__(self, root, path, logo_path):
        self.root, self.path, self.entries, self.stamp = root, path, [], None
        root.title(HISTORY_TITLE)
        root.geometry("860x600")
        root.minsize(520, 360)
        self.icon = ImageTk.PhotoImage(logo(logo_path, size=64))
        root.iconphoto(True, self.icon)
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont"):
            font.nametofont(name).configure(family="Segoe UI", size=10)
        line = font.nametofont("TkDefaultFont").metrics("linespace")
        style = ttk.Style()
        style.configure("Treeview", rowheight=int(line * 1.7))  # Tk doesn't scale row height with the display

        top = ttk.Frame(root, padding=(12, 12, 12, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.render())
        entry = ttk.Entry(top, textvariable=self.search)
        entry.pack(side="left", fill="x", expand=True, padx=8)
        self.count = ttk.Label(top, foreground="#6b7280")
        self.count.pack(side="right")

        panes = ttk.PanedWindow(root, orient="vertical")
        panes.pack(fill="both", expand=True, padx=12)
        listing = ttk.Frame(panes)
        self.tree = ttk.Treeview(listing, columns=("mode", "text"), selectmode="browse")
        for column, heading, width, stretch in (("#0", "When", 150, False), ("mode", "Mode", 100, False),
                                                ("text", "Dictation", 500, True)):
            self.tree.heading(column, text=heading, anchor="w")
            self.tree.column(column, width=width, minwidth=60, stretch=stretch, anchor="w")
        self.tree.tag_configure("day", font=("Segoe UI Semibold", 10))
        scroll = ttk.Scrollbar(listing, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        panes.add(listing, weight=3)

        reading = ttk.Frame(panes)
        self.detail = tk.Text(reading, wrap="word", height=8, font=("Segoe UI", 11), relief="flat",
                              padx=10, pady=8, borderwidth=0, highlightthickness=1, highlightcolor="#d1d5db")
        self.detail.tag_configure("muted", foreground="#6b7280", font=("Segoe UI", 10))
        detail_scroll = ttk.Scrollbar(reading, command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")
        panes.add(reading, weight=2)

        bottom = ttk.Frame(root, padding=12)
        bottom.pack(fill="x")
        self.copy_button = ttk.Button(bottom, text="Copy", command=lambda: self.copy("cleaned"))
        self.copy_button.pack(side="left")
        self.copy_raw_button = ttk.Button(bottom, text="Copy original", command=lambda: self.copy("raw"))
        self.copy_raw_button.pack(side="left", padx=8)
        self.status = ttk.Label(bottom, foreground="#16a34a")
        self.status.pack(side="left", padx=4)
        ttk.Label(bottom, text="Double-click or Enter copies  ·  Ctrl+F searches  ·  Updates live",
                  foreground="#6b7280").pack(side="right")

        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show())
        self.tree.bind("<Double-1>", lambda _: self.copy("cleaned"))
        self.tree.bind("<Return>", lambda _: self.copy("cleaned"))
        root.bind("<Control-f>", lambda _: entry.focus_set())
        entry.bind("<Escape>", lambda _: self.search.set(""))
        self.poll()

    def selected(self):
        """Index into self.entries of the selected dictation, or None (nothing, or a day heading)."""
        sel = self.tree.selection()
        return int(sel[0]) if sel and sel[0].isdigit() else None

    def poll(self):
        """Reload when history.jsonl changes (a stat once a second is all this costs while idle)."""
        try:
            stat = self.path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            stamp = None
        if stamp != self.stamp:
            # Follow new dictations unless the user has picked an older one to look at.
            follow = self.selected() in (None, len(self.entries) - 1)
            self.stamp, self.entries = stamp, history.read(self.path)
            self.render(follow_newest=follow)
        self.root.after(1000, self.poll)

    def render(self, follow_newest=False):
        q = self.search.get().strip().lower()
        keep = self.selected()
        self.tree.delete(*self.tree.get_children())
        shown = []
        for i in reversed(range(len(self.entries))):  # newest first
            e = self.entries[i]
            if q and q not in f"{e.get('cleaned', '')} {e.get('raw', '')}".lower():
                continue
            day, time = when(e["timestamp"])
            if not self.tree.exists(day):
                self.tree.insert("", "end", iid=day, text=day, open=True, tags=("day",))
            self.tree.insert(day, "end", iid=str(i), text=time,
                             values=(e.get("mode", ""), " ".join(e.get("cleaned", "").split())))
            shown.append(i)
        total = len(self.entries)
        self.count.configure(text=f"{len(shown)} of {total}" if q else f"{total} dictation{'s' * (total != 1)}")
        target = shown[0] if shown and (follow_newest or keep not in shown) else keep
        if target is not None and target in shown:
            self.tree.selection_set(str(target))
            self.tree.see(str(target))
        self.show()

    def show(self):
        i = self.selected()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if i is None:
            self.detail.insert("end", "No dictations yet. Hold Ctrl+Win and speak." if not self.entries
                               else "Nothing matches your search.", "muted")
            edited = False
        else:
            e = self.entries[i]
            self.detail.insert("end", e.get("cleaned", ""))
            edited = e.get("raw") and e.get("raw") != e.get("cleaned")
            if edited:
                self.detail.insert("end", "\n\nWhat you said:\n" + e["raw"], "muted")
        self.detail.configure(state="disabled")
        self.copy_button.state(["!disabled"] if i is not None else ["disabled"])
        self.copy_raw_button.state(["!disabled"] if edited else ["disabled"])

    def copy(self, field):
        i = self.selected()
        if i is None:
            return
        pyperclip.copy(self.entries[i].get(field, ""))
        self.status.configure(text="Copied" if field == "cleaned" else "Original copied")
        self.root.after(1500, lambda: self.status.configure(text=""))


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on scaled displays
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    HistoryWindow(root, Path(sys.argv[1]), Path(sys.argv[2]))
    root.mainloop()
