# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

The user-facing product name is **MorasFlow.si** (`APP_NAME` in `tray.py`); "VoiceFlow" survives only in internal names (folder, `voiceflow.log`, the single-instance mutex), which stay put because paths and running copies depend on them. The repo is public on GitHub (MIT). `setup.bat` (root) is the installer for other people: venv, pinned `requirements.txt`, `.env` and `vocab.txt` from their `.example` files, then `voiceflow/install.py`, which builds the desktop icon and creates the `MorasFlow.si.lnk` Desktop/Start-menu shortcuts. The logo is chosen by `logo:` in `config.yaml` (`logo.png` is the user's avatar, `logo-mic.png` the generic alternative); `tray.logo()` cuts it to a circle, with a grey/red/amber state ring in the tray. `install.py` names the icon `icon-<hash of image>.ico` because Explorer caches icons by path. Keep personal data out of tracked files: `vocab.txt` (the user's real list, with employer/client names), `.env`, history, logs, `*.wav` and `*.ico` are gitignored; `README.md` is at the repo root.

`SPEC.md` is the source of truth for VoiceFlow: a Windows 11 push-to-talk dictation app in Python 3.11+ (hold hotkey, speak, release, cleaned text is pasted into the active window). Read it before any work.

All seven milestones in `SPEC.md` are built. For new work, keep the same rhythm: one change at a time, then stop so the user can test it. All code lives in `voiceflow/`.

## Commands

The venv is Python 3.12 (`py -3.12 -m venv .venv`); the system default is 3.14, which faster-whisper's native deps may not support.

```
setup.bat                                   # full install for end users (venv, packages, shortcuts)
.venv/Scripts/python -m pip install -r voiceflow/requirements.txt
.venv/Scripts/python voiceflow/main.py      # dev run with console output
.venv/Scripts/pythonw voiceflow/main.py     # silent run (autostart via shell:startup)
```

There is no automated test suite; acceptance tests are manual (see `SPEC.md`, "Acceptance tests"). `voiceflow/transcriber.py` and `voiceflow/cleaner.py` have `__main__` self-checks that print `ok`. Global keyboard hooks receive no events (real or simulated) from Claude Code's shell tools, so test the pipeline by importing `main` and monkeypatching (`main.keyboard.is_pressed`, `main.recorder`, `paster.keyboard.send`); the hotkey itself can only be tested by the user.

When testing, don't launch a live copy while the user's VoiceFlow is running: a named mutex makes the second copy pop a modal "already running" message box. Stub `ctypes.windll.user32.MessageBoxW` and `tray.Tray.run`, and redirect `RotatingFileHandler` so test runs don't write to the user's `voiceflow.log`.

## Architecture

One pipeline per dictation, with each stage in its own module:

hotkey (`main.py`) → `recorder.py` (16 kHz mono float32) → discard if < 0.3 s → `transcriber.py` (`vad_filter=True`, `vocab.txt` joined as `initial_prompt`) → `replacements.yaml` substitutions → `cleaner.py` (LLM, mode prompt appended to the default cleanup prompt) → em dash replacement in code → `paster.py` (save clipboard, paste; restore 1.5 s later on a timer, and only if `GetClipboardSequenceNumber` shows nobody copied since: apps read the clipboard when they handle Ctrl+V, and Windows Terminal sometimes takes > 300 ms) → `history.save()` appends to `history.jsonl`. The tray's "Open history" starts `history_window.py` (Tkinter) as a separate `pythonw` process, or brings it forward via `FindWindowW(HISTORY_TITLE)`; it polls `history.jsonl`'s mtime/size once a second, so it updates live without any link to the app. "Copy recent dictation" is a tray submenu rebuilt by `tray.refresh()` after each save.

The mic stream stays open for the app's lifetime (WASAPI) and `Recorder.record()` only buffers while the hotkey is held: opening a stream on this machine takes ~0.5 s with every Windows host API, which would clip the first word. The hotkey callback only grabs the `busy` lock and spawns a worker thread, because with `suppress=True` it runs inside the keyboard hook. Modifier-only hotkeys (the default `ctrl+windows`) are registered with `suppress=False`: the `keyboard` library never matches them in suppress mode. They then call `mask_start_menu()` on each press so releasing Win doesn't open Start.

`main.py` loads `config.yaml` and `.env`, then `tray.run()` blocks the main thread (pystray); the keyboard hook and each dictation run on other threads. The tray and pipeline share a `state` namespace (`mode`, `cleanup`, `paused`): tray menu clicks write it, `dictate()` reads it. Toggle mode needs no extra state: `until_pressed_again()` is just a different `keep_going` for `Recorder.record()`.

Transcription (`local | groq | openai`) and cleanup (`anthropic | openai | groq | ollama`) backends are selected in `config.yaml`. API keys come from `.env` via `python-dotenv` only.

## Invariants

- Never lose what was said: if cloud transcription fails, local Whisper (lazy-loaded) transcribes instead; if cleanup fails, times out (`cleanup.timeout_seconds`, default 5 s), or its API key is missing, paste the raw transcript (and for a missing key, fall back to Raw mode and notify via tray).
- A single failed dictation must never crash the app; log, error beep, keep running.
- Load the local Whisper model at most once and keep it warm (at startup for `backend: local`, on the first cloud failure otherwise). Idle CPU near zero.
- No em dashes in output, ever. The prompt forbids them and code strips them as a safety net.
- Irish/UK English spelling in cleanup output.
- Target: under 1.5 s from key release to paste for a 10 s clip on CPU in Raw mode.
- Logs go to `voiceflow.log` with rotation, never dictated text (that's only in `history.jsonl`). Nothing leaves the machine except the optional API calls.
- Under `pythonw` there is no console: startup failures must surface via `fatal()` (message box), runtime problems via `tray.notify()` and the log.
