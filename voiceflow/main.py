import ctypes
import logging
import sys
import threading
import time
import winsound
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import SimpleNamespace

import keyboard
import yaml
from dotenv import load_dotenv

import history
from cleaner import MODES, Cleaner
from paster import paste
from recorder import SAMPLE_RATE, TAIL_SECONDS, Recorder
from transcriber import Transcriber
from tray import APP_NAME, Tray

HERE = Path(__file__).parent
LOG_PATH = HERE / "voiceflow.log"
MIN_SECONDS = 0.3
BEEPS = {"start": (880, 60), "paste": (1320, 60), "error": (220, 300)}  # Hz, ms
MASK_VK = 0xE8  # unassigned virtual key; the keyboard library reports it as scan code -0xE8

log = logging.getLogger("voiceflow")
busy = threading.Lock()
failing = set()  # parts ("transcription", "cleanup") whose failure the user has already been told about


def setup_logging():
    handlers = [RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
    if sys.stderr:  # None under pythonw: there is no console
        handlers.append(logging.StreamHandler())
    # Root at WARNING keeps faster-whisper's and httpx's per-request INFO chatter out; our logger logs INFO.
    logging.basicConfig(level=logging.WARNING, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.setLevel(logging.INFO)
    logging.captureWarnings(True)
    threading.excepthook = lambda a: log.error("Unhandled error", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def already_running():
    """True if the app is already running (two copies would paste every dictation twice)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, "Local\\VoiceFlow")  # the handle stays open until this process exits
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def fatal(message):
    """Startup can't continue: say why in a message box, since under pythonw there's no console."""
    log.error(message)
    # MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST: with no window of our own, a plain box opens behind others.
    ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10 | 0x10000 | 0x40000)
    sys.exit(1)


def modifier_only(hotkey):
    """True for hotkeys like ctrl+windows. The keyboard library never matches these in suppress mode, and as
    they type nothing they don't need suppressing anyway."""
    return all(keyboard.is_modifier(codes[0]) for codes in keyboard.parse_hotkey(hotkey)[0])


def mask_start_menu():
    """Releasing Win (or Alt) with no other key pressed meanwhile opens the Start menu (or a menu bar).
    Tapping an unassigned virtual key while it's held cancels that, like AutoHotkey's MenuMaskKey."""
    for flags in (0, 2):  # key down, then KEYEVENTF_KEYUP
        ctypes.windll.user32.keybd_event(MASK_VK, 0, flags, 0)


def beep(kind):
    if config["beeps"]["enabled"]:
        threading.Thread(target=winsound.Beep, args=BEEPS[kind], daemon=True).start()  # Beep blocks


def until_pressed_again():
    """Toggle mode: keep recording until the hotkey is released and then pressed again."""
    released = False

    def keep_going():
        nonlocal released
        pressed = keyboard.is_pressed(config["hotkey"])
        released = released or not pressed
        return not (released and pressed)
    return keep_going


def foreground_app():
    """Exe name of the active window, for diagnosing missed pastes. Never raises: a diagnostic must not cost
    the user their dictation."""
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        name, size = ctypes.create_unicode_buffer(260), ctypes.c_ulong(260)
        process = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        ok = process and kernel32.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size))
        if process:
            kernel32.CloseHandle(process)
        return Path(name.value).name if ok else "unknown app"
    except Exception as e:
        return f"unknown ({e!r})"


def held_keys():
    try:
        return "+".join(k for k in ("ctrl", "shift", "alt", "windows") if keyboard.is_pressed(k)) or "none"
    except Exception as e:
        return f"unknown ({e!r})"


def describe(error):
    """The API's own message where there is one: the SDKs' str() includes raw JSON."""
    body = getattr(error, "body", None)
    detail = body.get("error", body) if isinstance(body, dict) else None
    message = detail.get("message") if isinstance(detail, dict) else None
    return message or str(error) or type(error).__name__


def report(part, error, consequence):
    """Notify on a part's first failure, then stay quiet until it has worked again (no toast per dictation)."""
    if error is None:
        failing.discard(part)
    elif part not in failing:
        failing.add(part)
        tray.notify(f"{consequence}: {describe(error)}"[:250])


def dictate():
    # Another key pressed while the hotkey is held means a shortcut (Ctrl+Win+Left), not dictation: cancel.
    cancelled = threading.Event()

    def watch(e):
        if e.event_type == "down" and e.scan_code not in hotkey_codes and keyboard.is_pressed(config["hotkey"]):
            cancelled.set()

    try:
        tray.set_state("recording")
        beep("start")
        hold = until_pressed_again() if config["mode"] == "toggle" else lambda: keyboard.is_pressed(config["hotkey"])
        hook = keyboard.hook(watch)
        app_at_press = foreground_app()  # if focus moves mid-hold, the target may miss the hotkey's key-ups
        try:
            audio = recorder.record(lambda: hold() and not cancelled.is_set())
        finally:
            keyboard.unhook(hook)
        app_at_release = foreground_app()
        if cancelled.is_set():
            log.info("Cancelled: another key was pressed with the hotkey")
            return
        released = time.perf_counter() - TAIL_SECONDS
        seconds = len(audio) / SAMPLE_RATE
        if seconds < MIN_SECONDS:
            log.info("Discarded %.2fs tap", seconds)
            return
        tray.set_state("processing")
        raw = transcriber.transcribe(audio)
        report("transcription", transcriber.last_error, "Cloud transcription failed, used local Whisper")
        mode = state.mode if state.cleanup else "Raw"
        text = cleaner.clean(raw, mode)
        report("cleanup", cleaner.last_error, "Cleanup failed, pasted your words uncleaned")
        if not text:
            log.info("No speech in %.1fs of audio", seconds)
            return
        latency_ms = round((time.perf_counter() - released) * 1000)
        beep("paste")
        target, held = foreground_app(), held_keys()  # captured just before Ctrl+V is sent
        stale = paste(text, target)
        focus = app_at_press if app_at_press == app_at_release else f"{app_at_press} -> {app_at_release}"
        # Dictated text goes to history.jsonl (if enabled), never to the log.
        log.info("Pasted %d chars into %s (held: %s, stale in target: %s, focus during hold: %s): "
                 "%.1fs audio, %s mode, %d ms release to paste", len(text), target, held,
                 "+".join(stale) or "none", focus, seconds, mode, latency_ms)
        if config["history"]["enabled"]:
            history.save(history_path, mode, raw, text, latency_ms)
            tray.refresh()  # so "Recent dictations" includes this one
    except Exception:
        log.exception("Dictation failed")
        beep("error")
    finally:
        tray.set_state("idle")
        busy.release()


def on_hotkey():
    # Runs on the keyboard library's thread (inside the hook when suppressing): do nothing slow here.
    # Key repeat while held is ignored.
    if not suppress:
        mask_start_menu()  # every press, including the stop press in toggle mode
    if not state.paused and busy.acquire(blocking=False):
        threading.Thread(target=dictate, daemon=True).start()


if __name__ == "__main__":
    setup_logging()
    if already_running():
        fatal(f"{APP_NAME} is already running. Look for its icon in the system tray.")
    try:
        load_dotenv(HERE / ".env")
        config = yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))
        history_path = HERE / config["history"]["path"]
        state = SimpleNamespace(mode=config["default_mode"], cleanup=config["cleanup"]["enabled"], paused=False)
        log.info("Starting, loading speech model")
        t, c = config["transcription"], config["cleanup"]
        transcriber = Transcriber(t["backend"], t["model"], t["device"])
        cleaner = Cleaner(c["backend"], c["model"], c["timeout_seconds"])
        if cleaner.disabled_reason:
            state.mode = "Raw"
        recorder = Recorder()
        tray = Tray(state, MODES, HERE, history_path, recorder.set_paused, HERE / config["logo"])
        try:
            suppress = not modifier_only(config["hotkey"])  # stop e.g. ctrl+shift+space typing a space
            hotkey_codes = {c for codes in keyboard.parse_hotkey(config["hotkey"])[0] for c in codes} | {-MASK_VK}
            keyboard.add_hotkey(config["hotkey"], on_hotkey, suppress=suppress)
        except ValueError as e:
            raise RuntimeError(f"The hotkey '{config['hotkey']}' in config.yaml isn't a valid key combination.") from e
    except Exception as e:
        log.exception("Startup failed")
        fatal(f"{APP_NAME} couldn't start.\n\n{e}\n\nDetails: {LOG_PATH}")

    notices = [n for n in (transcriber.notice,
                           cleaner.disabled_reason and f"Cleanup off ({cleaner.disabled_reason}), using Raw mode.") if n]

    def ready():
        log.info("Ready. Mic: %s | transcription: %s / %s | cleanup: %s | %s %s to dictate",
                 recorder.device_name, transcriber.backend, transcriber.model,
                 cleaner.disabled_reason or f"{cleaner.backend} / {cleaner.model}",
                 "hold" if config["mode"] == "push_to_talk" else "press", config["hotkey"])
        if config["history"].get("open_on_start"):
            tray.open_history()
        if notices:
            log.warning(" ".join(notices))
        # pythonw has no window and Windows 11 hides new tray icons, so confirm we're running.
        # One toast for everything: a second would replace the first.
        action = "Hold" if config["mode"] == "push_to_talk" else "Press"
        tray.notify("\n".join([f"Running. {action} {config['hotkey']} to dictate."] + notices))

    tray.run(ready)
