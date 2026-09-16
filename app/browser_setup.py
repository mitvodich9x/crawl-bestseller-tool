"""Make sure Playwright's Chromium is installed (adapted from walmart-scanner-tool/main.py)."""
import os
import subprocess
import sys

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _browsers_dir() -> str:
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if override and override != "0":
        return override
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")


def chromium_installed() -> bool:
    """Both the full Chromium (visible login window) and the headless shell (background scans)."""
    root = _browsers_dir()
    if not os.path.isdir(root):
        return False
    names = os.listdir(root)
    has_full = any(n.startswith("chromium-") for n in names)
    has_shell = any(n.startswith("chromium_headless_shell-") for n in names)
    return has_full and has_shell


def install_command() -> list[str] | None:
    # the bundled driver works in frozen builds, where sys.executable is the app exe
    try:
        from playwright._impl._driver import compute_driver_executable
        parts = compute_driver_executable()
        if isinstance(parts, (list, tuple)) and len(parts) >= 2 and all(os.path.isfile(p) for p in parts[:2]):
            return [parts[0], parts[1], "install", "chromium"]
    except Exception:
        pass
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "playwright", "install", "chromium"]
    return None


def install_chromium(timeout_s: int = 900) -> tuple[bool, str]:
    command = install_command()
    if not command:
        return False, "Không tìm được lệnh cài Chromium"
    env = None
    try:
        from playwright._impl._driver import get_driver_env
        env = get_driver_env()
    except Exception:
        pass
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s,
                                env=env, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False, "Quá thời gian tải Chromium, kiểm tra kết nối mạng"
    except OSError as exc:
        return False, str(exc)
    if result.returncode == 0:
        return True, "Đã cài Chromium"
    return False, (result.stderr or result.stdout or "Lỗi không xác định").strip()[-500:]
