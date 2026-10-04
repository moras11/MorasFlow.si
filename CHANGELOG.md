# Changelog

## [1.1.0] - 2026-10-04

### Added
- Live History window (tray > Open history): every dictation, grouped by day, search as you type, Copy and Copy original, light and dark mode. Opens when the app starts (`history.open_on_start`).
- Tray > Copy recent dictation: your last 10, one click to copy.
- `config.local.yaml` for your own settings: kept out of git and across updates.
- The version shows in the tray tooltip and the log.

### Fixed
- Windows Terminal and other slow apps could paste your previous clipboard instead of the dictation. The clipboard now comes back only after the app has actually read the dictation.
- Pastes into Windows Terminal could silently fail after Ctrl+Win, because it still thought Win was held.
- A copy you made between two quick dictations could be overwritten.
- A failed paste lost the dictation; it's now saved to History first, and any failure shows a notification.
- One damaged line in `history.jsonl` could stop the app starting or freeze the tray menu.
- A mistyped `default_mode` made every dictation fail; it's now reported at startup.
- An error while updating the tray icon could leave the hotkey dead.
- Some API error messages could put dictated text in `voiceflow.log`.
- New installs lost dictations when offline: setup now fetches the offline speech model.
- Setup: Python 3.11 couldn't install the packages and 3.14 was refused (now 3.12 to 3.14, rebuilding old environments); `.env.example` had two keys on one line.
- Switching transcription to `local` failed on the Groq model name: models now default per backend.
- The tray menu and History search were slow with a large history.

### Changed
- Dictations no longer appear in Windows clipboard history (Win+V).
- New installs get the plain mic logo; set `logo: logo.png` for the avatar.

## [1.0.0] - 2026-10-04

Initial public release.
