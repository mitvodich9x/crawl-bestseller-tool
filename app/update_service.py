"""Tự cập nhật qua GitHub Releases (repo công khai, không cần token hay server riêng).

Windows không cho ghi đè file .exe đang chạy, nên bản mới được giải nén ra thư mục tạm rồi
một file .bat phụ chờ app thoát, copy đè lên thư mục cài và mở lại app.
Thư mục data (database, cài đặt, phiên đăng nhập) được giữ nguyên.
"""
import json
import logging
import os
import re
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.app_version import APP_VERSION
from app.paths import app_dir, data_dir

log = logging.getLogger(__name__)

GITHUB_REPO = "mitvodich9x/crawl-bestseller-tool"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "BestsellerCrawler"}
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


@dataclass
class ReleaseInfo:
    version: str
    name: str
    notes: str
    page_url: str
    asset_url: str | None
    asset_name: str | None
    asset_size: int


def parse_version(value: str) -> tuple[int, ...]:
    """'v0.2.0' / '0.2' -> (0, 2, 0). Phần không phải số bị bỏ qua."""
    numbers = re.findall(r"\d+", value or "")
    parts = tuple(int(n) for n in numbers[:3])
    return parts + (0,) * (3 - len(parts))


def is_newer(latest: str, current: str = APP_VERSION) -> bool:
    return parse_version(latest) > parse_version(current)


def parse_release(payload: dict) -> ReleaseInfo:
    asset = next((a for a in payload.get("assets") or []
                  if (a.get("name") or "").lower().endswith(".zip")), None)
    return ReleaseInfo(
        version=(payload.get("tag_name") or "").lstrip("vV"),
        name=payload.get("name") or payload.get("tag_name") or "",
        notes=payload.get("body") or "",
        page_url=payload.get("html_url") or RELEASES_PAGE,
        asset_url=asset.get("browser_download_url") if asset else None,
        asset_name=asset.get("name") if asset else None,
        asset_size=int(asset.get("size") or 0) if asset else 0,
    )


def fetch_latest(timeout: int = 20) -> ReleaseInfo:
    request = urllib.request.Request(LATEST_RELEASE_URL, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_release(json.load(response))


def can_self_update() -> bool:
    """Chỉ bản đóng gói (.exe) mới thay được file; bản chạy từ source thì dùng git pull."""
    return bool(getattr(sys, "frozen", False))


def staging_dir() -> Path:
    path = data_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def download_asset(release: ReleaseInfo, progress_cb=lambda done, total: None,
                   should_stop=lambda: False) -> Path:
    if not release.asset_url:
        raise RuntimeError("Bản phát hành không có file .zip để tải")
    target = staging_dir() / (release.asset_name or "update.zip")
    request = urllib.request.Request(release.asset_url, headers={"User-Agent": "BestsellerCrawler"})
    with urllib.request.urlopen(request, timeout=60) as response, open(target, "wb") as out:
        total = int(response.headers.get("Content-Length") or release.asset_size or 0)
        done = 0
        while chunk := response.read(256 * 1024):
            if should_stop():
                raise RuntimeError("Đã huỷ tải bản cập nhật")
            out.write(chunk)
            done += len(chunk)
            progress_cb(done, total)
    return target


def extract(zip_path: Path) -> Path:
    target = staging_dir() / "new"
    if target.exists():
        _remove_tree(target)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)
    exe = target / "BestsellerCrawler.exe"
    if not exe.exists():
        raise RuntimeError("File cập nhật không đúng cấu trúc (thiếu BestsellerCrawler.exe)")
    return target


def _remove_tree(path: Path) -> None:
    import shutil
    shutil.rmtree(path, ignore_errors=True)


def _updater_script(new_dir: Path, install_dir: Path | None = None, exe: Path | None = None,
                    pid: int | None = None) -> str:
    install_dir = install_dir or app_dir()
    exe = exe or Path(sys.executable)
    pid = os.getpid() if pid is None else pid
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        f'set "APPDIR={install_dir}"\r\n'
        f'set "NEWDIR={new_dir}"\r\n'
        f'set "EXEPATH={exe}"\r\n'
        f'set "APPPID={pid}"\r\n'
        "rem cho app dang chay thoat han truoc khi ghi de\r\n"
        ":waitloop\r\n"
        'tasklist /FI "PID eq %APPPID%" 2>nul | find "%APPPID%" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        "  ping -n 2 127.0.0.1 >nul\r\n"
        "  goto waitloop\r\n"
        ")\r\n"
        "rem /PURGE xoa file thua cua ban cu, /XD giu nguyen thu muc data\r\n"
        'robocopy "%NEWDIR%" "%APPDIR%" /E /PURGE /XD "%APPDIR%\\data" /R:3 /W:2 /NFL /NDL /NJH /NJS >nul\r\n'
        "if errorlevel 8 (\r\n"
        '  echo Cap nhat that bai, mo lai ban cu.\r\n'
        ")\r\n"
        'start "" "%EXEPATH%"\r\n'
        'rmdir /s /q "%NEWDIR%" 2>nul\r\n'
        '(goto) 2>nul & del "%~f0"\r\n'
    )


def apply_update(new_dir: Path) -> None:
    """Khởi chạy script thay file rồi trả về; phía gọi phải thoát app ngay sau đó."""
    script = staging_dir() / "apply_update.bat"
    script.write_text(_updater_script(new_dir), encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(script)], cwd=str(staging_dir()), creationflags=_NO_WINDOW,
                     close_fds=True)
    log.info("Đã khởi chạy script cập nhật: %s", script)
