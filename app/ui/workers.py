"""Background threads. Playwright's sync API stays entirely inside the thread that created it."""
import logging

from PyQt6.QtCore import QThread, pyqtSignal

from app import browser_setup, update_service
from app.errors import friendly_error
from app.core.scan_job import ScanCallbacks, run_scan
from app.db.database import Database
from app.paths import browser_profile_dir
from app.scraper.watchcount import ChallengeError, WatchcountClient

log = logging.getLogger(__name__)


def _ensure_chromium(emit) -> bool:
    browser_setup.configure_env()
    if browser_setup.chromium_installed():
        return True
    emit("Đang tải trình duyệt Chromium lần đầu (~200MB), vui lòng chờ...")
    ok, msg = browser_setup.install_chromium()
    emit(msg)
    return ok


class ScanWorker(QThread):
    log_line = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)
    attention = pyqtSignal(str)  # cần người dùng tích reCAPTCHA trong cửa sổ trình duyệt
    done = pyqtSignal(object)  # ScanSummary | None

    def __init__(self, db: Database, cfg: dict, keywords: list[str], trigger: str):
        super().__init__()
        self.db, self.cfg, self.keywords, self.trigger = db, cfg, keywords, trigger
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        summary = None
        try:
            if _ensure_chromium(self.log_line.emit):
                callbacks = ScanCallbacks(log=self.log_line.emit, progress=self.progress.emit,
                                          should_stop=lambda: self._stop, attention=self.attention.emit)
                summary = run_scan(self.db, self.cfg, self.keywords, self.trigger, callbacks)
        except Exception as exc:
            log.exception("Scan worker crashed")
            self.log_line.emit(f"Lỗi: {exc}")
        self.done.emit(summary)


class UpdateCheckWorker(QThread):
    """Hỏi GitHub bản phát hành mới nhất. done: (ReleaseInfo | None, error str | None)."""

    done = pyqtSignal(object, object)

    def run(self) -> None:
        try:
            self.done.emit(update_service.fetch_latest(), None)
        except Exception as exc:
            log.info("Update check failed: %s", exc)
            self.done.emit(None, str(exc))


class UpdateDownloadWorker(QThread):
    progress = pyqtSignal(int, int)  # bytes tải xong, tổng bytes
    done = pyqtSignal(object, object)  # file cài đặt / thư mục đã giải nén | None, lỗi | None

    def __init__(self, release):
        super().__init__()
        self.release = release
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            downloaded = update_service.download_asset(self.release, self.progress.emit, lambda: self._stop)
            self.done.emit(update_service.prepare(downloaded), None)
        except Exception as exc:
            log.warning("Update download failed: %s", exc)
            self.done.emit(None, str(exc))


class AccountWorker(QThread):
    """mode='check': headless status read. mode='login': visible window, waits for the user to sign in."""

    log_line = pyqtSignal(str)
    done = pyqtSignal(object)  # {"logged_in": bool, "usage": dict} | {"error": str}

    def __init__(self, mode: str, headless: bool = True):
        super().__init__()
        self.mode = mode
        self.headless = headless
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        result: dict
        client = None
        try:
            if not _ensure_chromium(self.log_line.emit):
                raise RuntimeError("Chưa cài được Chromium")
            client = WatchcountClient(browser_profile_dir(), headless=self.headless and self.mode == "check")
            client.start()
            if self.mode == "login":
                self.log_line.emit("Đã mở trình duyệt, hãy đăng nhập watchcount trong cửa sổ đó...")
                if not client.interactive_login(should_stop=lambda: self._stop):
                    raise RuntimeError("Chưa đăng nhập (cửa sổ bị đóng hoặc quá thời gian chờ)")
                # qua reCAPTCHA luôn trong cửa sổ này, để các lần quét ẩn sau không bị chặn
                self.log_line.emit("Đang mở thử 1 trang tìm kiếm để qua xác minh reCAPTCHA "
                                   "(tích \"I'm not a robot\" nếu được hỏi)...")
                try:
                    client.pass_challenge(should_stop=lambda: self._stop)
                    self.log_line.emit("Đã qua xác minh reCAPTCHA")
                except ChallengeError:
                    self.log_line.emit("Chưa qua xác minh reCAPTCHA; lần quét tới sẽ mở lại cửa sổ để xác minh")
            result = client.account_status()
        except Exception as exc:
            log.warning("Account %s failed: %s", self.mode, exc)
            result = {"error": friendly_error(exc)}
        finally:
            if client:
                client.close()
        self.done.emit(result)
