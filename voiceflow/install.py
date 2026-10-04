"""Run by setup.bat: fetch the offline speech model, build the desktop icon from the configured `logo`, then
(re)create the Desktop and Start menu shortcuts for wherever this folder lives. Safe to run again, e.g. after
changing the logo."""
import base64
import hashlib
import subprocess
import sys
from pathlib import Path

from main import load_config
from transcriber import DEFAULT_MODELS, load_whisper
from tray import APP_NAME, logo

HERE = Path(__file__).parent


def build_icon(config):
    # Windows caches icons by file path, so the name carries a hash of the image: a new logo means a new path.
    source = HERE / config["logo"]
    path = HERE / f"icon-{hashlib.sha1(source.read_bytes()).hexdigest()[:8]}.ico"
    for old in HERE.glob("*.ico"):
        old.unlink()
    logo(source).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def create_shortcuts(icon):
    quote = lambda s: "'" + str(s).replace("'", "''") + "'"  # PowerShell single-quoted string
    script = f"""$ProgressPreference = 'SilentlyContinue'
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in 'Desktop', 'Programs') {{
    $s = $shell.CreateShortcut([Environment]::GetFolderPath($folder) + '\\{APP_NAME}.lnk')
    $s.TargetPath = {quote(Path(sys.executable).with_name("pythonw.exe"))}
    $s.Arguments = {quote(f'"{HERE / "main.py"}"')}
    $s.WorkingDirectory = {quote(HERE)}
    $s.IconLocation = {quote(f"{icon},0")}
    $s.Description = 'Push-to-talk dictation'
    $s.Save()
}}"""
    # -EncodedCommand sidesteps command-line quoting for paths with spaces or quotes.
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded], check=True)


if __name__ == "__main__":
    config = load_config()
    # Cloud transcription falls back to this model when there's no internet, which is exactly when it can't be
    # downloaded, so fetch it now (once; a no-op when already cached).
    model = config["transcription"].get("model") if config["transcription"]["backend"] == "local" else None
    print(f"Checking the offline speech model (first time: a ~480 MB download)...")
    load_whisper(model or DEFAULT_MODELS["local"], "cpu")
    create_shortcuts(build_icon(config))
    print(f"Created {APP_NAME} shortcuts on the Desktop and in the Start menu.")
