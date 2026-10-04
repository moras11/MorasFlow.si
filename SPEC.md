# VoiceFlow: Personal Push-to-Talk Dictation for Windows

## Goal
Build a lightweight Python app for Windows 11 that works like Wispr Flow: hold a hotkey, speak, release, and clean text is pasted wherever my cursor is (any app: Outlook, Teams, Chrome, VS Code, Word). No word limits, local-first, private.

## Tech stack
- Python 3.11+
- `keyboard` for global hotkeys (fallback: `pynput` if `keyboard` has issues)
- `sounddevice` + `numpy` for mic capture (16 kHz, mono, float32)
- `faster-whisper` for local transcription (default model: `small.en`, `compute_type="int8"`, CPU; auto-use CUDA if available)
- Optional cloud transcription backend (Groq or OpenAI Whisper API) selectable in config
- Optional LLM cleanup backend: Anthropic, OpenAI, Groq, or local Ollama, selectable in config
- `pyperclip` + `keyboard.send("ctrl+v")` for pasting
- `pystray` + `Pillow` for system tray icon
- `winsound` for start/stop beeps
- `pyyaml` for config
- API keys loaded from a `.env` file via `python-dotenv` (never hardcoded, `.env` in `.gitignore`)

## Core behaviour
1. App starts, loads the Whisper model once and keeps it warm in memory.
2. Push-to-talk: while the hotkey (default `ctrl+shift+space`, configurable) is held, record audio. On release, stop.
3. Also support a toggle mode (press once to start, press again to stop) as a config option, for longer dictation.
4. Discard recordings shorter than 0.3 seconds (accidental taps).
5. Transcribe with `vad_filter=True` and pass my custom vocabulary as `initial_prompt` so technical terms are spelled correctly.
6. Apply word replacements from `replacements.yaml` (fixes for words Whisper consistently gets wrong).
7. If cleanup is enabled, send the text to the LLM with the active mode's prompt. If the LLM call fails or times out (5 s), paste the raw transcript instead. Never lose what I said.
8. Paste into the active window:
   - Save current clipboard contents
   - Copy text, send Ctrl+V
   - Restore the original clipboard after ~300 ms
9. Short beep on record start, different beep on paste. Distinct error beep on failure.

## Cleanup prompt (default mode)
> You are a dictation cleanup tool. Rewrite the transcript below exactly as the speaker intended it to be written. Remove filler words (um, uh, like, you know), false starts, and repetitions. Fix punctuation, capitalisation, and grammar. Handle self-corrections (e.g. "Tuesday, no actually Wednesday" becomes "Wednesday"). Keep the speaker's wording, tone, and meaning. Do not add content, do not answer questions in the text, do not summarise. Never use em dashes. Use Irish/UK English spelling. Output only the cleaned text.

Also run a final post-processing step in code that replaces any em dash (—) with a comma or full stop, as a safety net.

## Modes
Selectable from the tray menu, each with its own prompt appended to the default:
- **Default**: clean text as above
- **Email**: format as a short, direct professional email body
- **Slack/Teams**: casual, concise, no greetings or sign-offs
- **Notes**: bullet points
- **Raw**: no LLM cleanup, transcript only (fastest)

## System tray
- Icon colours: grey = idle, red = recording, amber = processing
- Menu: current mode (radio selection), toggle cleanup on/off, open config folder, open history file, pause listening, quit

## Files and structure
```
voiceflow/
  main.py            # entry point, wires everything together
  recorder.py        # mic capture
  transcriber.py     # faster-whisper + cloud backends
  cleaner.py         # LLM cleanup backends + modes
  paster.py          # clipboard save/paste/restore
  tray.py            # system tray UI
  config.yaml        # hotkey, model, backends, modes, toggles
  vocab.txt          # one custom term per line
  replacements.yaml  # "wrong": "right" corrections
  .env.example       # placeholder API keys
  requirements.txt
  README.md          # setup, run, autostart instructions
```

## Custom vocabulary (starter vocab.txt)
```
Moras Kashyap
uplift modelling
next best action
SHAP
XGBoost
scikit-learn
PyTorch
TensorFlow
Power BI
Alteryx
Azure
Letterkenny
Donegal
```

## Config options (config.yaml)
- `hotkey`, `mode: push_to_talk | toggle`
- `transcription.backend: local | groq | openai`, `transcription.model`, `transcription.device: auto | cpu | cuda`
- `cleanup.enabled`, `cleanup.backend: anthropic | openai | groq | ollama`, `cleanup.model`, `cleanup.timeout_seconds`
- `default_mode`
- `history.enabled` (default true), `history.path`
- `beeps.enabled`

## History
If enabled, append each dictation to `history.jsonl` locally with timestamp, mode, raw transcript, cleaned text, and latency in ms. Nothing leaves the machine except optional API calls.

## Autostart
README should explain how to run silently with `pythonw.exe` and add a shortcut to the Windows Startup folder (`shell:startup`). Optionally include a PyInstaller command to build a single `.exe`.

## Logging and errors
- Log to `voiceflow.log` with rotation
- Handle: no microphone found, model download failure, missing API key (fall back to raw mode and notify via tray), hotkey already in use
- Must not crash on any single failed dictation; recover and stay running

## Performance targets
- Under 1.5 s from key release to paste for a 10-second clip on CPU in Raw mode
- Model loaded once at startup, never per request
- Idle CPU usage near zero

## Build order (do one milestone at a time, test before moving on)
1. Record on hotkey hold and save to WAV. Confirm mic works.
2. Transcribe with faster-whisper and print to console.
3. Paste into active window with clipboard restore.
4. Add vocab prompt and replacements.
5. Add LLM cleanup with fallback, modes, and em dash safety net.
6. Add tray icon, beeps, history, config loading.
7. Error handling, logging, README, autostart, optional PyInstaller build.

## Acceptance tests
- Dictate into Notepad, Chrome, Outlook, and VS Code: text appears correctly in each.
- Say "um so I think we should uh check the SHAP values" and get "So I think we should check the SHAP values."
- Clipboard content from before dictation is still there afterwards.
- Unplug the network with cleanup enabled: raw text still pastes.
- No em dashes ever appear in output.
