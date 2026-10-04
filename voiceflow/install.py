"""Run by setup.bat: build the desktop icon from config.yaml's `logo`, then (re)create the Desktop and Start menu
shortcuts for wherever this folder lives. Safe to run again, e.g. after changing the logo."""
import base64
import hashlib
import subprocess
import sys
from pathlib import Path

import yaml

from tray import APP_NAME, logo

HERE = Path(__file__).parent


def build_icon():
    # Windows caches icons by file path, so the name carries a hash of the image: a new logo means a new path.
    source = HERE / yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))["logo"]
    path = HERE / f"icon-{hashlib.sha1(source.read_bytes()).hexdigest()[:8]}.ico"
    for old in HERE.glob("*.ico"):
        old.unlink()
    logo(source).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def create_shortcuts(icon):
    quote = lambda s: "'" + str(s).replace("'", "''") + "'"  # PowerShell single-quoted string
    script = f"""
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
    create_shortcuts(build_icon())
    print(f"Created {APP_NAME} shortcuts on the Desktop and in the Start menu.")
