"""Start with Windows via a hidden .vbs launcher in the user's Startup folder (no admin needed)."""
import os
import sys
from pathlib import Path

from app.app_version import APP_ID
from app.paths import app_dir


def _startup_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def launcher_path() -> Path:
    return _startup_dir() / f"{APP_ID}.vbs"


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else exe
    return f'"{interpreter}" "{app_dir() / "main.py"}" --minimized'


def is_enabled() -> bool:
    return launcher_path().exists()


def set_enabled(enabled: bool) -> None:
    path = launcher_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    command = _command().replace('"', '""')
    script = (
        'Set shell = CreateObject("WScript.Shell")\r\n'
        f'shell.CurrentDirectory = "{app_dir()}"\r\n'
        f'shell.Run "{command}", 0, False\r\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script, encoding="utf-8")
