import io
import json
import zipfile
from pathlib import Path

import pytest

from app import update_service


@pytest.mark.parametrize("value,expected", [
    ("v0.2.0", (0, 2, 0)),
    ("0.1.0", (0, 1, 0)),
    ("v1.2", (1, 2, 0)),
    ("v1.10.3-beta", (1, 10, 3)),
    ("", (0, 0, 0)),
])
def test_parse_version(value, expected):
    assert update_service.parse_version(value) == expected


@pytest.mark.parametrize("latest,current,expected", [
    ("v0.2.0", "0.1.0", True),
    ("v0.1.0", "0.1.0", False),
    ("v0.1.0", "0.2.0", False),
    ("v0.10.0", "0.9.0", True),  # so sánh số, không so chuỗi
    ("v1.0.0", "0.9.9", True),
])
def test_is_newer(latest, current, expected):
    assert update_service.is_newer(latest, current) is expected


def test_parse_release_picks_zip_asset():
    payload = {
        "tag_name": "v0.2.0",
        "name": "v0.2.0 — bản mới",
        "body": "Ghi chú",
        "html_url": "https://github.com/x/y/releases/tag/v0.2.0",
        "assets": [
            {"name": "notes.txt", "browser_download_url": "https://x/notes.txt", "size": 10},
            {"name": "BestsellerCrawler-0.2.0.zip", "browser_download_url": "https://x/app.zip", "size": 1234},
        ],
    }
    release = update_service.parse_release(payload)
    assert release.version == "0.2.0"
    assert release.asset_name == "BestsellerCrawler-0.2.0.zip"
    assert release.asset_url == "https://x/app.zip"
    assert release.asset_size == 1234


def test_parse_release_without_asset():
    release = update_service.parse_release({"tag_name": "v0.3.0", "assets": []})
    assert release.asset_url is None
    assert release.page_url == update_service.RELEASES_PAGE


def _make_zip(tmp_path: Path, names: list[str]) -> Path:
    path = tmp_path / "update.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(name, "x")
    return path


def test_extract_accepts_valid_package(tmp_path, monkeypatch):
    monkeypatch.setattr(update_service, "staging_dir", lambda: tmp_path / "staging")
    (tmp_path / "staging").mkdir()
    zip_path = _make_zip(tmp_path, ["BestsellerCrawler.exe", "_internal/base_library.zip"])
    folder = update_service.extract(zip_path)
    assert (folder / "BestsellerCrawler.exe").exists()


def test_extract_rejects_package_without_exe(tmp_path, monkeypatch):
    monkeypatch.setattr(update_service, "staging_dir", lambda: tmp_path / "staging")
    (tmp_path / "staging").mkdir()
    zip_path = _make_zip(tmp_path, ["readme.txt"])
    with pytest.raises(RuntimeError, match="cấu trúc"):
        update_service.extract(zip_path)


def test_updater_script_keeps_data_folder_and_waits_for_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(update_service, "app_dir", lambda: Path(r"C:\App"))
    script = update_service._updater_script(tmp_path / "new")
    assert "/PURGE" in script  # dọn file thừa của bản cũ
    assert r'/XD "%APPDIR%\data"' in script  # nhưng giữ nguyên dữ liệu người dùng
    assert "waitloop" in script and "tasklist" in script  # chờ app thoát rồi mới ghi đè
    assert 'start "" "%EXEPATH%"' in script  # mở lại app sau khi xong


def test_download_asset_writes_file_and_reports_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(update_service, "staging_dir", lambda: tmp_path)
    payload = b"z" * (600 * 1024)

    class FakeResponse(io.BytesIO):
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(update_service.urllib.request, "urlopen", lambda *a, **k: FakeResponse(payload))
    release = update_service.ReleaseInfo("0.2.0", "n", "", "url", "https://x/app.zip", "app.zip", len(payload))
    seen = []
    path = update_service.download_asset(release, lambda done, total: seen.append((done, total)))
    assert path.read_bytes() == payload
    assert seen[-1] == (len(payload), len(payload))


def test_download_asset_can_be_cancelled(tmp_path, monkeypatch):
    monkeypatch.setattr(update_service, "staging_dir", lambda: tmp_path)

    class FakeResponse(io.BytesIO):
        headers = {"Content-Length": "999999"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(update_service.urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"z" * 999999))
    release = update_service.ReleaseInfo("0.2.0", "n", "", "url", "https://x/app.zip", "app.zip", 999999)
    with pytest.raises(RuntimeError, match="huỷ"):
        update_service.download_asset(release, should_stop=lambda: True)


def test_fetch_latest_parses_github_payload(monkeypatch):
    payload = json.dumps({"tag_name": "v9.9.9", "assets": [
        {"name": "a.zip", "browser_download_url": "https://x/a.zip", "size": 5}]}).encode()

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(update_service.urllib.request, "urlopen", lambda *a, **k: FakeResponse(payload))
    release = update_service.fetch_latest()
    assert release.version == "9.9.9"
    assert update_service.is_newer(release.version) is True
