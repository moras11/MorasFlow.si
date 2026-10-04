# MorasFlow.si

*By Moras Kashyap, built with Claude.*

Push-to-talk dictation for Windows. Hold **Ctrl+Win**, speak, release, and clean, punctuated text is pasted wherever your cursor is: Outlook, Teams, Chrome, VS Code, Word, Windows Terminal, anything.

- **Fast**: about a second from releasing the keys to the text appearing.
- **Free**: transcription and cleanup run on Groq's free tier (no card needed).
- **Cleans up as you'd write it**: removes "um" and "uh", false starts and repetitions, handles self-corrections ("Tuesday, no actually Wednesday" becomes "Wednesday"), and fixes punctuation. UK/Irish spelling, never em dashes.
- **Modes**: Default, Email, Slack/Teams, Notes (bullet points) and Raw.
- **Never loses what you said**: if transcription fails it falls back to an offline speech model on your PC; if cleanup fails it pastes your words uncleaned; every dictation is saved to History before it's pasted.
- **Your words, your spelling**: a custom word list for names and jargon, plus automatic fixes for words it keeps getting wrong.

## Requirements

- Windows 10 or 11 and a microphone
- [Python](https://www.python.org/downloads/) 3.12, 3.13 or 3.14 (the python.org installer includes the `py` launcher that setup uses)
- A free [Groq API key](https://console.groq.com/keys). Optional, but without it transcription runs on your PC (slower) and there's no cleanup.

## Setup

1. Download the [latest release](https://github.com/moras11/MorasFlow.si/releases/latest) (**Source code (zip)**, then unzip it somewhere outside OneDrive) or `git clone` this repo.
2. Double-click **`setup.bat`**. It installs everything into a `.venv` folder inside the app, fetches the offline speech model (the first run takes a few minutes and downloads about 0.5 GB), and adds **MorasFlow.si** to your Desktop and Start menu.
3. When Notepad opens `voiceflow\.env`, paste your Groq key after `GROQ_API_KEY=` and save.
4. Start **MorasFlow.si** from the Desktop or Start menu. After a few seconds a "Running" notification appears, the History window opens, and the icon sits in the system tray (click **^** next to the clock if you can't see it).

**Start with Windows**: press Win+R, type `shell:startup`, and copy the MorasFlow.si shortcut from your Desktop into that folder.

If you move the folder, run `setup.bat` again to fix the shortcuts.

## Using it

- **Hold Ctrl+Win, speak, release.** A high beep means recording started, a higher one means the text was pasted, and a low one means something failed. Taps under 0.3 s are ignored, and pressing any other key during the hold cancels (so Windows shortcuts like Ctrl+Win+Left still work).
- **Tray icon**: a grey ring when idle, red while recording, amber while processing. Hover to see the version. Right-click it for:
  - **Modes**: Default (clean up), Email (short professional email body), Slack/Teams (casual, no greetings or sign-offs), Notes (bullet points), Raw (exactly what you said, fastest)
  - **Copy recent dictation**: your last 10, newest first; click one to copy it (handy when the cursor was in the wrong place)
  - **Open history**: a window with every dictation, newest first and grouped by day, that updates live as you dictate. Search as you type; click one to read it in full, then **Copy** (or double-click). **Copy original** gives your exact words when cleanup changed them. Opens when the app starts (`history.open_on_start`), follows Windows light or dark mode, and clicking it again brings the open window to the front
  - **Cleanup** on/off, **Pause listening** (also releases the mic), **Open config folder**, **Quit**
- If something fails (no internet, Groq down, an invalid key, a paste that couldn't happen) you get one notification saying what happened, not one per dictation.
- Your clipboard comes back once the app you dictated into has read the text (text only: a copied image or file is lost). If you copy something yourself in the meantime, yours is kept.

## Settings

All in the `voiceflow` folder. Restart MorasFlow.si after editing.

| File | What it does |
|---|---|
| `config.local.yaml` | **Your settings.** Anything you put here overrides `config.yaml`; create it if it isn't there. Updates and git leave it alone |
| `config.yaml` | The defaults, with every option explained: hotkey, hold or toggle mode, logo, transcription and cleanup backends and models, timeout, default mode, history, beeps |
| `vocab.txt` | Names and terms to spell correctly, one per line (about 70 max). Created from `vocab.example.txt` by setup |
| `replacements.yaml` | `"wrong": "right"` fixes for words that keep coming out wrong |
| `.env` | API keys: `GROQ_API_KEY`, plus `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` if you switch backends |

For example, a `config.local.yaml` that switches to toggle mode and Claude for cleanup:

```yaml
mode: toggle
cleanup:
  backend: anthropic
```

**Your own logo**: set `logo:` in `config.local.yaml` to any image in the `voiceflow` folder: `logo-mic.png` (the default), `logo.png` (Moras's avatar), or your own. It's cut to a circle, and non-square images are centre-cropped. Then run `setup.bat` again to update the desktop icon.

**Other backends**: cleanup also works with Anthropic (Claude), OpenAI, or a local [Ollama](https://ollama.com) model, and transcription with OpenAI or fully offline (`transcription.backend: local`). Leave `model` blank and each backend uses its own default.

## Updating

Your settings and history live in the app's `voiceflow` folder: `.env`, `config.local.yaml`, `vocab.txt`, `history.jsonl`, and `replacements.yaml` if you edited it.

- **If you cloned with git**: quit MorasFlow.si, `git pull`, run `setup.bat` again.
- **If you downloaded a ZIP**: quit MorasFlow.si, unzip the new release into a new folder, copy those files across, run `setup.bat` in the new folder, then delete the old folder. If you start it with Windows, copy the new Desktop shortcut into `shell:startup` again.

## Uninstall

Quit MorasFlow.si, then delete the app folder, the MorasFlow.si shortcuts (Desktop, Start menu, and `shell:startup` if you added one), and the downloaded speech model in `%USERPROFILE%\.cache\huggingface`.

## Privacy

- With the default settings your audio and text go to Groq for transcription and cleanup. Set `transcription.backend: local` and turn Cleanup off to keep everything on your PC.
- `history.jsonl` keeps every dictation (time, mode, raw and cleaned text, latency) in the app folder; turn it off with `history.enabled: false`. If the app folder is inside OneDrive, OneDrive will sync it. `voiceflow.log` records what happened but never what you said.
- Dictations are kept out of Windows clipboard history (Win+V) and cloud clipboard sync.
- Your keys (`.env`), settings, word list, history and log are excluded from git.
- While running, the mic stays open so recording starts instantly, so Windows shows its mic-in-use icon. **Pause listening** releases it.

## Troubleshooting

- **It didn't start**: startup problems (no microphone, a mistake in your settings, model download) show a message box. Everything else is in `voiceflow\voiceflow.log`.
- **"Already running"**: only one copy runs at a time; look for the icon in the tray.
- **Setup says Python is needed**: install Python 3.12 or newer from python.org and run `setup.bat` again. Setup rebuilds an environment made with an older Python by itself.
- **Slow**: with Groq, a dictation takes about a second. Offline transcription takes ~3 s per 10 s of speech on a typical laptop (`model: base.en` under `transcription` is faster but less accurate). Raw mode skips cleanup.
- **Nothing pasted**: your words are in History (tray > Open history, or Copy recent dictation). Windows also blocks keystrokes into apps running as administrator unless MorasFlow.si runs as administrator too.
- **Two dictation apps react**: close other dictation apps that use Ctrl+Win (e.g. Wispr Flow), or set a different `hotkey` (e.g. `ctrl+shift+space`).
- **Changed or unplugged the mic**: it uses the default mic from when it started, so quit and start it again.
- **The desktop icon didn't change after a new logo**: run `setup.bat` again, then press F5 on the Desktop.

## For developers

```
.venv\Scripts\python voiceflow\main.py          # run with the log in the console
.venv\Scripts\python voiceflow\transcriber.py   # self-check: word replacements
.venv\Scripts\python voiceflow\cleaner.py       # self-check: cleanup fallbacks and em dash safety net
```

`SPEC.md` is the original specification, `CLAUDE.md` explains the architecture (written for Claude Code, readable by anyone), and `CHANGELOG.md` lists what changed in each version.

## Licence

MIT. See [LICENSE](LICENSE).
