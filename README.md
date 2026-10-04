# MorasFlow.si

*By Moras Kashyap, built with Claude.*

Push-to-talk dictation for Windows. Hold **Ctrl+Win**, speak, release, and clean, punctuated text is pasted wherever your cursor is: Outlook, Teams, Chrome, VS Code, Word, anything.

- **Fast**: under a second from releasing the keys to the text appearing.
- **Free**: transcription and cleanup run on Groq's free tier (no card needed).
- **Cleans up as you'd write it**: removes "um" and "uh", false starts and repetitions, handles self-corrections ("Tuesday, no actually Wednesday" becomes "Wednesday"), and fixes punctuation. UK/Irish spelling, never em dashes.
- **Modes**: Default, Email, Slack/Teams, Notes (bullet points) and Raw.
- **Never loses what you said**: if transcription fails it falls back to an offline speech model on your PC; if cleanup fails it pastes your words uncleaned.
- **Your words, your spelling**: a custom word list for names and jargon, plus automatic fixes for words it keeps getting wrong.

## Requirements

- Windows 10 or 11 and a microphone
- [Python 3.12](https://www.python.org/downloads/) (3.11 and 3.13 also work). Keep the "py launcher" option ticked when installing.
- A free [Groq API key](https://console.groq.com/keys). Optional, but without it transcription runs on your PC (slower) and there's no cleanup.

## Setup

1. Download this repo (**Code → Download ZIP**, then unzip it) or `git clone` it.
2. Double-click **`setup.bat`**. It installs everything into a `.venv` folder inside the app (the first run takes a few minutes) and adds **MorasFlow.si** to your Desktop and Start menu.
3. When Notepad opens `voiceflow\.env`, paste your Groq key after `GROQ_API_KEY=` and save.
4. Start **MorasFlow.si** from the Desktop or Start menu. After a few seconds a "Running" notification appears and the icon sits in the system tray (click **^** next to the clock if you can't see it).

**Start with Windows**: press Win+R, type `shell:startup`, and copy the MorasFlow.si shortcut from your Desktop into that folder.

If you move the folder, run `setup.bat` again to fix the shortcuts.

## Using it

- **Hold Ctrl+Win, speak, release.** A high beep means recording started, a higher one means the text was pasted, and a low one means something failed. Taps under 0.3 s are ignored, and pressing any other key during the hold cancels (so Windows shortcuts like Ctrl+Win+Left still work).
- **Tray icon**: a grey ring when idle, red while recording, amber while processing. Right-click it for:
  - **Modes**: Default (clean up), Email (short professional email body), Slack/Teams (casual, no greetings or sign-offs), Notes (bullet points), Raw (exactly what you said, fastest)
  - **Cleanup** on/off, **Pause listening** (also releases the mic), **Open config folder**, **Open history**, **Quit**
- If something fails (no internet, Groq down, an invalid key) you get one notification saying what happened, not one per dictation.
- Your clipboard is restored after each paste (text only: a copied image or file is lost).

## Settings

All in the `voiceflow` folder. Restart MorasFlow.si after editing.

| File | What it does |
|---|---|
| `config.yaml` | Hotkey, hold or toggle mode, logo, transcription and cleanup backends and models, timeout, default mode, history, beeps |
| `vocab.txt` | Names and terms to spell correctly, one per line (about 70 max). Created from `vocab.example.txt` by setup |
| `replacements.yaml` | `"wrong": "right"` fixes for words that keep coming out wrong |
| `.env` | API keys: `GROQ_API_KEY`, plus `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` if you switch backends |

**Your own logo**: set `logo:` in `config.yaml` to any image in the `voiceflow` folder: `logo.png` (the default), `logo-mic.png` (a plain mic), or your own. It's cut to a circle, and non-square images are centre-cropped. Then run `setup.bat` again to update the desktop icon.

**Other backends**: cleanup also works with Anthropic (Claude), OpenAI, or a local [Ollama](https://ollama.com) model, and transcription with OpenAI or fully offline (`transcription.backend: local`), all set in `config.yaml`.

## Privacy

- With the default settings your audio and text go to Groq for transcription and cleanup. Set `transcription.backend: local` and turn Cleanup off to keep everything on your PC.
- `history.jsonl` keeps every dictation (time, mode, raw and cleaned text, latency) on your PC only; turn it off with `history.enabled: false`. `voiceflow.log` records what happened but never what you said.
- Your keys (`.env`), word list, history and log are excluded from git.
- While running, the mic stays open so recording starts instantly, so Windows shows its mic-in-use icon. **Pause listening** releases it.

## Troubleshooting

- **It didn't start**: startup problems (no microphone, bad `config.yaml`, model download) show a message box. Everything else is in `voiceflow\voiceflow.log`.
- **"Already running"**: only one copy runs at a time; look for the icon in the tray.
- **Slow**: with Groq, a dictation takes under a second. Offline transcription takes ~3 s per 10 s of speech on a typical laptop (`model: base.en` in `config.yaml` is faster but less accurate). Raw mode skips cleanup.
- **Nothing pastes into one particular app**: Windows blocks keystrokes into apps running as administrator unless MorasFlow.si also runs as administrator.
- **Two dictation apps react**: close other dictation apps that use Ctrl+Win (e.g. Wispr Flow), or change `hotkey` in `config.yaml` (e.g. `ctrl+shift+space`).
- **Changed or unplugged the mic**: it uses the default mic from when it started, so quit and start it again.
- **The desktop icon didn't change after a new logo**: run `setup.bat` again, then press F5 on the Desktop.

## For developers

```
.venv\Scripts\python voiceflow\main.py          # run with the log in the console
.venv\Scripts\python voiceflow\transcriber.py   # self-check: word replacements
.venv\Scripts\python voiceflow\cleaner.py       # self-check: cleanup fallbacks and em dash safety net
```

`SPEC.md` is the original specification, and `CLAUDE.md` explains the architecture (written for Claude Code, readable by anyone).

## Licence

MIT. See [LICENSE](LICENSE).
