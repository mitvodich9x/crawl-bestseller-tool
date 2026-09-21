"""Make sure Playwright's Chromium is installed (adapted from walmart-scanner-tool/main.py).

Playwright chọn thư mục trình duyệt theo biến môi trường PLAYWRIGHT_BROWSERS_PATH:
"0" nghĩa là tìm ngay trong thư mục cài app (bản đóng gói không có sẵn trình duyệt ở đó),
để trống thì dùng %LOCALAPPDATA%\\ms-playwright. Máy nào có sẵn biến này (do tool khác cài)
sẽ làm app tìm sai chỗ, nên app luôn tự ấn định một đường dẫn tuyệt đối của riêng mình.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def browsers_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "ms-playwright"
    return Path.home() / "AppData" / "Local" / "ms-playwright"


def configure_env() -> str:
    """Ghi đè PLAYWRIGHT_BROWSERS_PATH cho tiến trình hiện tại. Gọi trước khi dùng Playwright."""
    path = str(browsers_dir())
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") != path:
        log.info("Đặt PLAYWRIGHT_BROWSERS_PATH=%s", path)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = path
    return path


def _has_executable(prefix: str, exe_name: str) -> bool:
    """Tìm <thư mục trình duyệt>/<prefix>*/<thư mục con>/<exe_name>.

    Thư mục con khác nhau tuỳ loại (chrome-win64, chrome-headless-shell-win64) và có thể
    đổi theo phiên bản, nên dò bằng glob thay vì ghi cứng.
    """
    root = browsers_dir()
    if not root.is_dir():
        return False
    return any(folder.name.startswith(prefix) and any(folder.glob(f"*/{exe_name}"))
               for folder in root.iterdir() if folder.is_dir())


def chromium_installed() -> bool:
    """Cần cả Chromium đầy đủ (cửa sổ đăng nhập) và headless shell (quét nền).

    Kiểm tra tới tận file .exe, vì thư mục có thể còn lại sau một lần tải hỏng.
    """
    configure_env()
    return (_has_executable("chromium-", "chrome.exe")
            and _has_executable("chromium_headless_shell-", "chrome-headless-shell.exe"))


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
    target = configure_env()
    command = install_command()
    if not command:
        return False, "Không tìm được lệnh cài Chromium"
    env = os.environ.copy()
    try:
        from playwright._impl._driver import get_driver_env
        env = get_driver_env()
    except Exception:
        pass
    env["PLAYWRIGHT_BROWSERS_PATH"] = target  # tải đúng chỗ app sẽ tìm
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s,
                                env=env, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False, "Quá thời gian tải Chromium, kiểm tra kết nối mạng"
    except OSError as exc:
        return False, str(exc)
    if result.returncode == 0:
        if not chromium_installed():
            return False, f"Tải xong nhưng không thấy Chromium trong {target}"
        return True, "Đã cài Chromium"
    return False, (result.stderr or result.stdout or "Lỗi không xác định").strip()[-500:]
