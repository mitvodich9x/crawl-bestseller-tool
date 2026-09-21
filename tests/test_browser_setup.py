import os

import pytest

from app import browser_setup
from app.errors import friendly_error


@pytest.fixture
def fake_browsers(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_setup, "browsers_dir", lambda: tmp_path)
    return tmp_path


CHROMIUM = ("chromium-1228", "chrome-win64", "chrome.exe")
HEADLESS = ("chromium_headless_shell-1228", "chrome-headless-shell-win64", "chrome-headless-shell.exe")


def _make_browser(root, spec):
    folder, subdir, exe = spec
    path = root / folder / subdir
    path.mkdir(parents=True)
    (path / exe).write_bytes(b"x")


def test_configure_env_overrides_zero_from_another_tool(monkeypatch, tmp_path):
    """Máy lỗi có PLAYWRIGHT_BROWSERS_PATH=0 -> playwright tìm trong thư mục app."""
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    result = browser_setup.configure_env()
    assert result == str(tmp_path / "ms-playwright")
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == result


def test_configure_env_overrides_other_tools_path(monkeypatch, tmp_path):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", r"D:\tool khac\browsers")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert browser_setup.configure_env() == str(tmp_path / "ms-playwright")


def test_browsers_dir_without_localappdata(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert browser_setup.browsers_dir().name == "ms-playwright"


def test_chromium_installed_needs_both_executables(fake_browsers, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(fake_browsers))
    assert browser_setup.chromium_installed() is False
    _make_browser(fake_browsers, CHROMIUM)
    assert browser_setup.chromium_installed() is False  # còn thiếu headless shell
    _make_browser(fake_browsers, HEADLESS)
    assert browser_setup.chromium_installed() is True


def test_chromium_installed_matches_real_playwright_layout(fake_browsers, monkeypatch):
    """Tên thư mục con khác nhau giữa chromium và headless shell (bug bản 0.2.0)."""
    monkeypatch.setenv("LOCALAPPDATA", str(fake_browsers))
    _make_browser(fake_browsers, ("chromium-1228", "chrome-win64", "chrome.exe"))
    _make_browser(fake_browsers, ("chromium_headless_shell-1228", "chrome-headless-shell-win64",
                                  "chrome-headless-shell.exe"))
    assert browser_setup.chromium_installed() is True


def test_chromium_installed_false_when_folder_exists_but_exe_missing(fake_browsers, monkeypatch):
    """Lần tải trước bị hỏng: có thư mục nhưng không có file chạy."""
    monkeypatch.setenv("LOCALAPPDATA", str(fake_browsers))
    (fake_browsers / "chromium-1228" / "chrome-win64").mkdir(parents=True)
    (fake_browsers / "chromium_headless_shell-1228" / "chrome-win64").mkdir(parents=True)
    assert browser_setup.chromium_installed() is False


def test_install_chromium_downloads_into_app_folder(fake_browsers, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(fake_browsers))
    monkeypatch.setattr(browser_setup, "install_command", lambda: ["cmd"])
    captured = {}

    class Result:
        returncode = 0
        stdout = stderr = ""

    def fake_run(command, **kwargs):
        captured["env"] = kwargs["env"]
        _make_browser(fake_browsers, CHROMIUM)
        _make_browser(fake_browsers, HEADLESS)
        return Result()

    monkeypatch.setattr(browser_setup.subprocess, "run", fake_run)
    ok, message = browser_setup.install_chromium()
    assert ok, message
    assert captured["env"]["PLAYWRIGHT_BROWSERS_PATH"] == str(fake_browsers)


def test_install_chromium_reports_when_nothing_was_downloaded(fake_browsers, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(fake_browsers))
    monkeypatch.setattr(browser_setup, "install_command", lambda: ["cmd"])

    class Result:
        returncode = 0
        stdout = stderr = ""

    monkeypatch.setattr(browser_setup.subprocess, "run", lambda *a, **k: Result())
    ok, message = browser_setup.install_chromium()
    assert ok is False
    assert "không thấy Chromium" in message


def test_friendly_error_explains_missing_browser():
    message = friendly_error(Exception(
        r"BrowserType.launch_persistent_context: Executable doesn't exist at "
        r"D:\tool\Trend Ebay\_internal\playwright\driver\package\.local-browsers\chromium-1208\chrome.exe"))
    assert "Chromium" in message and "mạng" in message
    assert "Executable doesn't exist" not in message


def test_friendly_error_keeps_short_unknown_message():
    assert friendly_error(Exception("Lỗi lạ\ndòng hai")) == "Lỗi lạ"
