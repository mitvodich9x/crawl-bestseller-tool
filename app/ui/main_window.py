import copy
import logging
from datetime import date, datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMenu, QMessageBox,
                             QProgressBar, QProgressDialog, QPushButton, QStackedWidget, QSystemTrayIcon,
                             QVBoxLayout, QWidget)

from app import autostart, config, update_service
from app.app_version import APP_NAME, APP_VERSION
from app.core import scheduler
from app.db.database import Database
from app.ui.pages.keywords_page import KeywordsPage
from app.ui.pages.log_page import LogPage
from app.ui.pages.results_page import ResultsPage
from app.ui.pages.schedule_page import SchedulePage
from app.ui.pages.settings_page import SettingsPage
from app.ui.style import app_icon
from app.ui.workers import AccountWorker, ScanWorker, UpdateCheckWorker, UpdateDownloadWorker

log = logging.getLogger(__name__)

SCHEDULE_CHECK_MS = 30_000


class MainWindow(QMainWindow):
    def __init__(self, db: Database, cfg: dict):
        super().__init__()
        self.db = db
        self.cfg = cfg
        self.scan_worker: ScanWorker | None = None
        self.account_worker: AccountWorker | None = None
        self.update_check_worker: UpdateCheckWorker | None = None
        self.update_download_worker: UpdateDownloadWorker | None = None
        self._update_dialog: QProgressDialog | None = None
        self._quitting = False
        self._no_keyword_warned: str | None = None

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setWindowIcon(app_icon())
        self.resize(1320, 860)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(200)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Bestseller\nCrawler")
        title.setObjectName("appTitle")
        side_layout.addWidget(title)
        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        side_layout.addWidget(self.nav, 1)
        layout.addWidget(side)

        content = QWidget()
        content.setObjectName("contentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self._build_top_bar())
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        layout.addWidget(content, 1)
        self.setCentralWidget(central)

        self.results_page = ResultsPage(db, lambda: copy.deepcopy(self.cfg["scan_filters"]))
        self.keywords_page = KeywordsPage(db)
        self.settings_page = SettingsPage(cfg)
        self.schedule_page = SchedulePage(cfg)
        self.log_page = LogPage(db)
        for label, page in (("Kết quả", self.results_page), ("Từ khoá", self.keywords_page),
                            ("Cài đặt quét", self.settings_page), ("Lịch quét", self.schedule_page),
                            ("Nhật ký", self.log_page)):
            self.nav.addItem(label)
            wrapper = QWidget()
            wrapper_layout = QVBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(16, 12, 16, 12)
            wrapper_layout.addWidget(page)
            self.stack.addWidget(wrapper)
        self.nav.currentRowChanged.connect(self._on_nav)
        self.nav.setCurrentRow(0)

        self.settings_page.save_requested.connect(self._save_settings)
        self.settings_page.login_requested.connect(lambda: self._run_account("login"))
        self.settings_page.check_account_requested.connect(lambda: self._run_account("check"))
        self.settings_page.check_update_requested.connect(lambda: self.check_update(silent=False))
        self.schedule_page.save_requested.connect(self._save_schedule)

        self._build_tray()
        self._schedule_timer = QTimer(self, interval=SCHEDULE_CHECK_MS)
        self._schedule_timer.timeout.connect(self._check_schedule)
        self._schedule_timer.start()
        QTimer.singleShot(5000, self._check_schedule)
        QTimer.singleShot(8000, lambda: self.check_update(silent=True))
        self._sync_autostart()

    # ---- layout ---------------------------------------------------------------------------

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("topBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 10, 16, 10)
        self.status_label = QLabel("Sẵn sàng")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.setVisible(False)
        self.scan_btn = QPushButton("▶ Quét ngay")
        self.scan_btn.setObjectName("primaryButton")
        self.stop_btn = QPushButton("■ Dừng")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.setEnabled(False)
        row.addWidget(self.status_label, 1)
        row.addWidget(self.progress)
        row.addWidget(self.scan_btn)
        row.addWidget(self.stop_btn)
        self.scan_btn.clicked.connect(lambda: self.start_scan("manual"))
        self.stop_btn.clicked.connect(self.stop_scan)
        return bar

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        show_action = QAction("Mở cửa sổ", self)
        scan_action = QAction("Quét ngay", self)
        quit_action = QAction("Thoát hẳn", self)
        show_action.triggered.connect(self.show_normal)
        scan_action.triggered.connect(lambda: self.start_scan("manual"))
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addAction(scan_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_normal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _on_nav(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        page = self.stack.currentWidget().layout().itemAt(0).widget()
        if page is self.results_page:
            self.results_page.refresh()
        elif page is self.log_page:
            self.log_page.reload_runs()
        elif page is self.schedule_page:
            self.schedule_page.refresh_status()

    def show_normal(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---- settings -------------------------------------------------------------------------

    def _save_config(self) -> None:
        config.save(self.cfg)

    def _save_settings(self) -> None:
        self.settings_page.write_to_config()
        self._save_config()
        self._sync_autostart()
        self.settings_page.load_from_config()
        self.status_label.setText("Đã lưu cài đặt")

    def _save_schedule(self) -> None:
        self.schedule_page.write_to_config()
        self._save_config()
        self.schedule_page.refresh_status()
        self.status_label.setText("Đã lưu lịch quét")

    def _sync_autostart(self) -> None:
        try:
            autostart.set_enabled(bool(self.cfg["general"]["autostart"]))
        except OSError as exc:
            log.warning("Autostart update failed: %s", exc)

    # ---- account --------------------------------------------------------------------------

    def _browser_busy(self) -> bool:
        return bool((self.scan_worker and self.scan_worker.isRunning())
                    or (self.account_worker and self.account_worker.isRunning()))

    def _run_account(self, mode: str) -> None:
        if self._browser_busy():
            QMessageBox.information(self, APP_NAME, "Trình duyệt đang được dùng (đang quét hoặc đăng nhập).")
            return
        self.settings_page.set_account_busy(True)
        self.settings_page.account_label.setText(
            "Đang mở trình duyệt để đăng nhập..." if mode == "login" else "Đang kiểm tra tài khoản...")
        self.account_worker = AccountWorker(mode, headless=True)
        self.account_worker.log_line.connect(self._log)
        self.account_worker.done.connect(self._on_account_done)
        self.account_worker.start()

    def _on_account_done(self, result: dict) -> None:
        self.settings_page.set_account_busy(False)
        self.settings_page.show_account(result)
        if result.get("logged_in"):
            self._log("Tài khoản watchcount: đã đăng nhập")

    # ---- update ---------------------------------------------------------------------------

    def check_update(self, silent: bool = True) -> None:
        """silent=True: kiểm tra nền lúc mở app, chỉ báo khi có bản mới."""
        if self.update_check_worker and self.update_check_worker.isRunning():
            return
        if not silent:
            self.settings_page.update_btn.setEnabled(False)
            self.settings_page.update_label.setText("Đang kiểm tra...")
        self.update_check_worker = UpdateCheckWorker()
        self.update_check_worker.done.connect(lambda release, error: self._on_update_checked(release, error, silent))
        self.update_check_worker.start()

    def _on_update_checked(self, release, error, silent: bool) -> None:
        self.settings_page.update_btn.setEnabled(True)
        if error:
            if not silent:
                self.settings_page.update_label.setText(f"❌ Không kiểm tra được: {error}")
            return
        if not update_service.is_newer(release.version):
            self.settings_page.update_label.setText(f"✅ Đang dùng bản mới nhất ({APP_VERSION})")
            return

        link = f'<a href="{release.page_url}">{release.page_url}</a>'
        self.settings_page.update_label.setText(f"🔔 Có bản mới: {release.version}. {link}")
        if silent and not self.isVisible():
            self.tray.showMessage(APP_NAME, f"Có bản cập nhật {release.version}. Mở app để cài.",
                                  QSystemTrayIcon.MessageIcon.Information, 8000)
            return

        notes = (release.notes or "").strip()
        if len(notes) > 1200:
            notes = notes[:1200] + "..."
        if not update_service.can_self_update():
            QMessageBox.information(self, "Có bản cập nhật",
                                    f"Bản mới: {release.version} (đang dùng {APP_VERSION}).\n\n"
                                    f"Bản chạy từ source không tự cập nhật được, dùng git pull.\n{release.page_url}")
            return
        answer = QMessageBox.question(
            self, "Có bản cập nhật",
            f"Bản mới: {release.version} (đang dùng {APP_VERSION})\n"
            f"Dung lượng tải: {release.asset_size / 1024 / 1024:.1f} MB\n\n{notes}\n\n"
            "Tải và cài ngay? App sẽ tự mở lại sau khi cập nhật.\n"
            "Dữ liệu, cài đặt và phiên đăng nhập watchcount được giữ nguyên.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self._download_update(release)

    def _download_update(self, release) -> None:
        if self._browser_busy():
            QMessageBox.information(self, APP_NAME, "Đang quét, hãy chờ quét xong rồi cập nhật.")
            return
        self._update_dialog = QProgressDialog("Đang tải bản cập nhật...", "Huỷ", 0, 100, self)
        self._update_dialog.setWindowTitle("Cập nhật")
        self._update_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._update_dialog.setMinimumWidth(420)
        self._update_dialog.setAutoClose(False)
        self.update_download_worker = UpdateDownloadWorker(release)
        self._update_dialog.canceled.connect(self.update_download_worker.stop)
        self.update_download_worker.progress.connect(self._on_update_progress)
        self.update_download_worker.done.connect(lambda folder, error: self._on_update_downloaded(folder, error))
        self.update_download_worker.start()
        self._update_dialog.show()

    def _on_update_progress(self, done: int, total: int) -> None:
        if not self._update_dialog:
            return
        mb = done / 1024 / 1024
        if total:
            self._update_dialog.setValue(int(done * 100 / total))
            self._update_dialog.setLabelText(f"Đang tải bản cập nhật... {mb:.1f} / {total / 1024 / 1024:.1f} MB")
        else:
            self._update_dialog.setLabelText(f"Đang tải bản cập nhật... {mb:.1f} MB")

    def _on_update_downloaded(self, folder, error) -> None:
        if self._update_dialog:
            self._update_dialog.close()
            self._update_dialog = None
        if error:
            QMessageBox.warning(self, "Cập nhật", f"Không tải được bản cập nhật:\n{error}")
            return
        QMessageBox.information(self, "Cập nhật",
                                "Đã tải xong. App sẽ đóng lại và tự mở lên sau vài giây.")
        try:
            update_service.apply_update(folder)
        except Exception as exc:
            QMessageBox.warning(self, "Cập nhật", f"Không chạy được bước thay file:\n{exc}")
            return
        self.quit_app()

    # ---- scanning -------------------------------------------------------------------------

    def start_scan(self, trigger: str) -> bool:
        if self._browser_busy():
            if trigger == "manual":
                QMessageBox.information(self, APP_NAME, "Đang có tác vụ trình duyệt chạy, vui lòng chờ.")
            return False
        keywords = [k["keyword"] for k in self.db.list_keywords(enabled_only=True)]
        if not keywords:
            if trigger == "manual":
                QMessageBox.information(self, APP_NAME, "Chưa có từ khoá nào được bật. Vào mục Từ khoá để thêm.")
            else:
                self._log("Đến lịch quét nhưng chưa có từ khoá nào được bật")
            return False

        self.scan_worker = ScanWorker(self.db, copy.deepcopy(self.cfg), keywords, trigger)
        self.scan_worker.log_line.connect(self._log)
        self.scan_worker.progress.connect(self._on_progress)
        self.scan_worker.done.connect(self._on_scan_done)
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setRange(0, len(keywords))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status_label.setText(f"Đang quét {len(keywords)} từ khoá...")
        self._log(f"Bắt đầu quét ({'theo lịch' if trigger == 'schedule' else 'thủ công'})")
        self.scan_worker.start()
        return True

    def stop_scan(self) -> None:
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.stop()
            self.stop_btn.setEnabled(False)
            self.status_label.setText("Đang dừng...")

    def _on_progress(self, done: int, total: int, keyword: str) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        if keyword:
            self.status_label.setText(f"Đang quét '{keyword}' ({done + 1}/{total})")

    def _on_scan_done(self, summary) -> None:
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setVisible(False)
        if summary is None:
            self.status_label.setText("Quét lỗi, xem Nhật ký")
            message = "Quét lỗi, xem Nhật ký"
        else:
            message = (f"Xong: {summary.total_kept} sản phẩm đạt bộ lọc / {summary.total_found} tìm thấy, "
                       f"dùng {summary.pages_used} lượt")
            if summary.error:
                message += f" — {summary.error}"
            self.status_label.setText(message)
        self.results_page.refresh()
        self.log_page.reload_runs()
        if not self.isVisible():
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.MessageIcon.Information, 8000)

    def _check_schedule(self) -> None:
        now = datetime.now()
        if not scheduler.should_run(now, self.cfg["schedule"], self.cfg["state"].get("last_run_date")):
            return
        if self._browser_busy():
            return  # try again on the next tick
        today = date.today().isoformat()
        if not self.db.list_keywords(enabled_only=True):
            if self._no_keyword_warned != today:
                self._no_keyword_warned = today
                self._log("Đến lịch quét nhưng chưa có từ khoá nào được bật, sẽ quét khi có từ khoá")
            return
        # mark the day before starting so a failing scan doesn't retrigger every tick
        self.cfg["state"]["last_run_date"] = today
        self._save_config()
        self.schedule_page.refresh_status()
        self.start_scan("schedule")

    def _log(self, message: str) -> None:
        self.log_page.append(message)

    # ---- close / quit ---------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._quitting and self.cfg["general"]["minimize_to_tray"] and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            self.tray.showMessage(APP_NAME, "App vẫn chạy nền dưới khay hệ thống để quét theo lịch.",
                                  QSystemTrayIcon.MessageIcon.Information, 4000)
            return
        self._shutdown()
        event.accept()
        QApplication.quit()  # quitOnLastWindowClosed is off so the tray can keep the app alive

    def quit_app(self) -> None:
        self._quitting = True
        self._shutdown()
        QApplication.quit()

    def _shutdown(self) -> None:
        for worker in (self.scan_worker, self.account_worker):
            if worker and worker.isRunning():
                worker.stop()
                worker.wait(15000)
        self.tray.hide()
