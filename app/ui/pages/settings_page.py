from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from app.app_version import APP_VERSION
from app.scraper import watchcount
from app.ui.widgets.filter_editor import FilterEditor


class SettingsPage(QWidget):
    save_requested = pyqtSignal()
    login_requested = pyqtSignal()
    check_account_requested = pyqtSignal()
    check_update_requested = pyqtSignal()

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        root = QVBoxLayout(host)
        scroll.setWidget(host)
        outer.addWidget(scroll)

        # account
        account = QGroupBox("Tài khoản watchcount")
        acc_layout = QVBoxLayout(account)
        self.account_label = QLabel("Chưa kiểm tra")
        self.account_label.setWordWrap(True)
        acc_buttons = QHBoxLayout()
        self.login_btn = QPushButton("Đăng nhập watchcount (mở trình duyệt)")
        self.check_btn = QPushButton("Kiểm tra tài khoản && lượt còn lại")
        acc_buttons.addWidget(self.login_btn)
        acc_buttons.addWidget(self.check_btn)
        acc_buttons.addStretch(1)
        note = QLabel("Đăng nhập một lần trong cửa sổ trình duyệt của tool; phiên đăng nhập được giữ lại cho các lần "
                      "quét sau. Tool không lưu mật khẩu.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        acc_layout.addWidget(self.account_label)
        acc_layout.addLayout(acc_buttons)
        acc_layout.addWidget(note)
        root.addWidget(account)

        # version / update
        version_box = QGroupBox("Phiên bản && cập nhật")
        version_layout = QVBoxLayout(version_box)
        self.version_label = QLabel(f"Phiên bản đang dùng: {APP_VERSION}")
        self.update_label = QLabel("Chưa kiểm tra")
        self.update_label.setObjectName("hint")
        self.update_label.setWordWrap(True)
        self.update_label.setOpenExternalLinks(True)
        update_row = QHBoxLayout()
        self.update_btn = QPushButton("Kiểm tra cập nhật")
        update_row.addWidget(self.update_btn)
        update_row.addStretch(1)
        version_layout.addWidget(self.version_label)
        version_layout.addLayout(update_row)
        version_layout.addWidget(self.update_label)
        root.addWidget(version_box)

        # search
        search = QGroupBox("Tìm kiếm trên watchcount")
        form = QFormLayout(search)
        self.site = QComboBox()
        self.site.addItems(watchcount.SITES)
        self.sort_by = QComboBox()
        for key, label in watchcount.SORT_OPTIONS.items():
            self.sort_by.addItem(label, key)
        self.listing_type = QComboBox()
        for key, label in watchcount.LISTING_TYPES.items():
            self.listing_type.addItem(label, key)
        self.max_pages = QSpinBox(minimum=1, maximum=500)
        self.stop_after_empty = QSpinBox(minimum=1, maximum=100)
        self.take_all_pages = QCheckBox("Lấy hết các trang (không dừng sớm khi trang không có đơn)")
        self.delay_min = QDoubleSpinBox(minimum=0, maximum=120, decimals=1, suffix=" giây")
        self.delay_max = QDoubleSpinBox(minimum=0, maximum=300, decimals=1, suffix=" giây")
        self.reserve = QSpinBox(minimum=0, maximum=1000)
        self.headless = QCheckBox("Ẩn trình duyệt khi quét")
        form.addRow("eBay site", self.site)
        form.addRow("Sắp xếp", self.sort_by)
        form.addRow("Loại listing", self.listing_type)
        form.addRow("Số trang tối đa / từ khoá (20 SP/trang)", self.max_pages)
        form.addRow("Dừng từ khoá sau N trang liền không có đơn", self.stop_after_empty)
        form.addRow("", self.take_all_pages)
        form.addRow("Nghỉ giữa các trang: từ", self.delay_min)
        form.addRow("đến", self.delay_max)
        form.addRow("Chừa lại số lượt / ngày", self.reserve)
        form.addRow("", self.headless)
        quota_note = QLabel("Mỗi trang kết quả tốn 1 lượt. Gói Free: 200 lượt standard/ngày (Best Match, Newly Listed), "
                            "50 lượt Watch Count/ngày, 3 lượt Best Selling/tháng.")
        quota_note.setObjectName("hint")
        quota_note.setWordWrap(True)
        form.addRow(quota_note)
        root.addWidget(search)

        # scan filters
        filter_box = QGroupBox("Bộ lọc khi quét (sản phẩm đạt sẽ được đánh dấu)")
        filter_layout = QVBoxLayout(filter_box)
        self.filter_editor = FilterEditor()
        filter_layout.addWidget(self.filter_editor)
        hint = QLabel("Start ≤ N ngày cũng được gửi lên watchcount (lọc listing mới) để tiết kiệm lượt. "
                      "Sell one = số ngày trung bình bán được 1 đơn, vd ≤ 7 / 3 / 1.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        filter_layout.addWidget(hint)
        root.addWidget(filter_box)

        # general
        general = QGroupBox("Chung")
        gen_layout = QVBoxLayout(general)
        self.tray = QCheckBox("Đóng cửa sổ thì chạy nền dưới khay hệ thống (để lịch quét vẫn chạy)")
        self.autostart = QCheckBox("Khởi động cùng Windows")
        gen_layout.addWidget(self.tray)
        gen_layout.addWidget(self.autostart)
        root.addWidget(general)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_btn = QPushButton("Lưu cài đặt")
        save_btn.setObjectName("primaryButton")
        save_row.addWidget(save_btn)
        root.addLayout(save_row)
        root.addStretch(1)

        self.take_all_pages.toggled.connect(lambda on: self.stop_after_empty.setEnabled(not on))
        save_btn.clicked.connect(self.save_requested)
        self.login_btn.clicked.connect(self.login_requested)
        self.check_btn.clicked.connect(self.check_account_requested)
        self.update_btn.clicked.connect(self.check_update_requested)
        self.load_from_config()

    def load_from_config(self) -> None:
        s = self.cfg["search"]
        self.site.setCurrentText(s["site"])
        self.sort_by.setCurrentIndex(max(0, self.sort_by.findData(s["sort_by"])))
        self.listing_type.setCurrentIndex(max(0, self.listing_type.findData(s["listing_type"])))
        self.max_pages.setValue(int(s["max_pages"]))
        take_all = int(s["stop_after_empty_pages"]) <= 0
        self.take_all_pages.setChecked(take_all)
        self.stop_after_empty.setValue(int(s["stop_after_empty_pages"]) if not take_all else 3)
        self.stop_after_empty.setEnabled(not take_all)
        self.delay_min.setValue(float(s["delay_min"]))
        self.delay_max.setValue(float(s["delay_max"]))
        self.reserve.setValue(int(s["reserve_quota"]))
        self.headless.setChecked(bool(s["headless"]))
        self.filter_editor.set_rules(self.cfg["scan_filters"])
        self.tray.setChecked(bool(self.cfg["general"]["minimize_to_tray"]))
        self.autostart.setChecked(bool(self.cfg["general"]["autostart"]))

    def write_to_config(self) -> None:
        s = self.cfg["search"]
        s["site"] = self.site.currentText()
        s["sort_by"] = self.sort_by.currentData()
        s["listing_type"] = self.listing_type.currentData()
        if s["sort_by"] == "bestselling":
            s["listing_type"] = "fixedprice"  # watchcount only allows best selling on fixed-price listings
        s["max_pages"] = self.max_pages.value()
        s["stop_after_empty_pages"] = 0 if self.take_all_pages.isChecked() else self.stop_after_empty.value()
        s["delay_min"] = min(self.delay_min.value(), self.delay_max.value())
        s["delay_max"] = max(self.delay_min.value(), self.delay_max.value())
        s["reserve_quota"] = self.reserve.value()
        s["headless"] = self.headless.isChecked()
        self.cfg["scan_filters"] = self.filter_editor.rule_dicts()
        self.cfg["general"]["minimize_to_tray"] = self.tray.isChecked()
        self.cfg["general"]["autostart"] = self.autostart.isChecked()

    def set_account_busy(self, busy: bool) -> None:
        self.login_btn.setEnabled(not busy)
        self.check_btn.setEnabled(not busy)

    def show_account(self, result: dict) -> None:
        if "error" in result:
            self.account_label.setText(f"❌ {result['error']}")
            return
        usage = result.get("usage") or {}
        if not result.get("logged_in"):
            self.account_label.setText(
                f"⚠ Chưa đăng nhập (khách). Standard còn {watchcount.remaining_quota(usage, 'bestmatch')} lượt hôm nay.")
            return
        tier = (usage.get("tier") or {}).get("display_name", "?")
        parts = [f"✅ Đã đăng nhập: {usage.get('email', '')} — gói {tier}"]
        for key, label in (("bestmatch", "Standard / ngày"), ("watchcount", "Watch Count / ngày"),
                           ("bestselling", "Best Selling / tháng")):
            parts.append(f"{label}: còn {watchcount.remaining_quota(usage, key)}")
        if usage.get("resets_at"):
            parts.append(f"Hạn mức tháng reset: {usage['resets_at']}")
        self.account_label.setText("\n".join(parts))
