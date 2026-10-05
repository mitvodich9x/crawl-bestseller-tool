from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from app.app_version import APP_VERSION
from app.core import filters
from app.scraper import watchcount
from app.ui.widgets.filter_editor import FilterEditor


SOLD_FILTER_NOTE = ("Tab Sold: mỗi listing chỉ tính 1 đơn và Sell one chỉ là số ngày listing đã chạy, nên Tổng đơn, "
                    "Sell one, Số đơn trung bình / ngày bị bỏ qua khi quét tab này.")


def _price_box() -> QDoubleSpinBox:
    box = QDoubleSpinBox(minimum=0, maximum=1_000_000, decimals=2, prefix="$")
    box.setSpecialValueText("không lọc")  # 0 = không gửi lên watchcount
    return box


def _price_value(box: QDoubleSpinBox) -> float | None:
    return box.value() or None


class SettingsPage(QWidget):
    save_requested = pyqtSignal()
    login_requested = pyqtSignal()
    check_account_requested = pyqtSignal()
    check_update_requested = pyqtSignal()
    link_applied = pyqtSignal(str)  # từ khoá trong link vừa áp dụng ("" nếu link không có từ khoá)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._extra_params: dict = {}
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

        # paste a watchcount link
        link_box = QGroupBox("Dán link watchcount")
        link_layout = QVBoxLayout(link_box)
        link_row = QHBoxLayout()
        self.link_input = QLineEdit()
        self.link_input.setPlaceholderText("https://www.watchcount.com/sold/... (copy từ thanh địa chỉ trình duyệt)")
        self.link_btn = QPushButton("Áp dụng link")
        link_row.addWidget(self.link_input, 1)
        link_row.addWidget(self.link_btn)
        link_hint = QLabel("Lọc trên web watchcount như bình thường, copy link trang kết quả rồi dán vào đây. Tool tự điền "
                           "các ô bên dưới, thêm từ khoá trong link vào danh sách Từ khoá và lưu cài đặt.")
        link_hint.setObjectName("hint")
        link_hint.setWordWrap(True)
        link_layout.addLayout(link_row)
        link_layout.addWidget(link_hint)
        root.addWidget(link_box)

        # search
        search = QGroupBox("Tìm kiếm trên watchcount")
        form = QFormLayout(search)
        self.status = QComboBox()
        for key, label in watchcount.STATUS_OPTIONS.items():
            self.status.addItem(label, key)
        self.last_sold = QComboBox()
        for key, label in watchcount.LAST_SOLD_OPTIONS.items():
            self.last_sold.addItem(label, key)
        self.site = QComboBox()
        self.site.addItems(watchcount.SITES)
        self.sort_by = QComboBox()
        self.category = QComboBox()
        for key, label in watchcount.CATEGORIES.items():
            self.category.addItem(label, key)
        self.min_price = _price_box()
        self.max_price = _price_box()
        price_row = QHBoxLayout()
        price_row.addWidget(self.min_price)
        price_row.addWidget(QLabel("đến"))
        price_row.addWidget(self.max_price)
        self.exact_match = QCheckBox("Exact Match Keywords (chỉ lấy sản phẩm có đủ các chữ của từ khoá)")
        self.extra_label = QLabel()
        self.extra_label.setWordWrap(True)
        self.extra_clear_btn = QPushButton("Bỏ")
        extra_row = QHBoxLayout()
        extra_row.addWidget(self.extra_label, 1)
        extra_row.addWidget(self.extra_clear_btn)
        self.extra_host = QWidget()
        self.extra_host.setLayout(extra_row)
        extra_row.setContentsMargins(0, 0, 0, 0)
        self.condition = QComboBox()
        for key, label in watchcount.CONDITIONS.items():
            self.condition.addItem(label, key)
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
        form.addRow("Tab tìm kiếm", self.status)
        form.addRow("Có đơn trong vòng (tab Sold)", self.last_sold)
        form.addRow("eBay site", self.site)
        form.addRow("Danh mục", self.category)
        form.addRow("Sắp xếp", self.sort_by)
        form.addRow("Loại listing", self.listing_type)
        form.addRow("Tình trạng (Condition)", self.condition)
        form.addRow("Giá (USD) từ", price_row)
        form.addRow("", self.exact_match)
        self.extra_caption = QLabel("Tham số thêm từ link")
        form.addRow(self.extra_caption, self.extra_host)
        form.addRow("Số trang tối đa / từ khoá (20 SP/trang)", self.max_pages)
        form.addRow("Dừng từ khoá sau N trang liền không có đơn", self.stop_after_empty)
        form.addRow("", self.take_all_pages)
        form.addRow("Nghỉ giữa các trang: từ", self.delay_min)
        form.addRow("đến", self.delay_max)
        form.addRow("Chừa lại số lượt / ngày", self.reserve)
        form.addRow("", self.headless)
        quota_note = QLabel("Tab Sold chỉ hiện sản phẩm đã có người mua và chỉ sắp xếp được theo Best Match hoặc giá; "
                            "Watch Count, Newly Listed, Best Selling chỉ có ở tab Live.\n"
                            "Mỗi trang kết quả tốn 1 lượt. Gói Free: 200 lượt standard/ngày (Sold, Best Match, "
                            "Newly Listed, giá), 50 lượt Watch Count/ngày, 3 lượt Best Selling/tháng.\n"
                            "Danh mục, Giá, Exact Match lọc ngay trên watchcount (không tốn thêm lượt). Danh mục theo "
                            "eBay US; muốn chọn danh mục con thì lọc trên web rồi dán link.")
        quota_note.setObjectName("hint")
        quota_note.setWordWrap(True)
        form.addRow(quota_note)
        root.addWidget(search)

        # scan filters
        filter_box = QGroupBox("Bộ lọc khi quét (sản phẩm đạt sẽ được đánh dấu)")
        filter_layout = QVBoxLayout(filter_box)
        self.filter_editor = FilterEditor()
        filter_layout.addWidget(self.filter_editor)
        self.filter_hint = QLabel()
        self.filter_hint.setObjectName("hint")
        self.filter_hint.setWordWrap(True)
        filter_layout.addWidget(self.filter_hint)
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
        self.status.currentIndexChanged.connect(lambda _i: self._fill_sorts(self.sort_by.currentData()))
        save_btn.clicked.connect(self.save_requested)
        self.login_btn.clicked.connect(self.login_requested)
        self.check_btn.clicked.connect(self.check_account_requested)
        self.update_btn.clicked.connect(self.check_update_requested)
        self.link_btn.clicked.connect(self.apply_link)
        self.link_input.returnPressed.connect(self.apply_link)
        self.extra_clear_btn.clicked.connect(lambda: self._set_extra_params({}))
        self.load_from_config()

    def _fill_sorts(self, selected: str | None) -> None:
        """Mỗi tab chỉ cho một số kiểu sắp xếp; đổi tab thì nạp lại danh sách."""
        status = self.status.currentData()
        self.sort_by.clear()
        for key in watchcount.SORTS_BY_STATUS[status]:
            self.sort_by.addItem(watchcount.SORT_OPTIONS[key], key)
        self.sort_by.setCurrentIndex(max(0, self.sort_by.findData(watchcount.valid_sort(status, selected or ""))))
        self.last_sold.setEnabled(status == "sold")
        self._update_filter_hint(status)

    def _update_filter_hint(self, status: str) -> None:
        if status == "sold":
            self.filter_editor.set_disabled_fields(filters.SOLD_TAB_IGNORED, SOLD_FILTER_NOTE)
            self.filter_hint.setText(SOLD_FILTER_NOTE + "\nStart ≤ N ngày chỉ lọc trong tool (watchcount không lọc "
                                     "ngày đăng ở tab Sold). Muốn ra đúng số sản phẩm như trên web thì để trống ô Start.")
        else:
            self.filter_editor.set_disabled_fields(())
            self.filter_hint.setText("Start ≤ N ngày cũng được gửi lên watchcount (lọc listing mới) để tiết kiệm lượt. "
                                     "Sell one = số ngày trung bình bán được 1 đơn, vd ≤ 7 / 3 / 1.")

    def _set_category(self, category: str) -> None:
        """Danh mục con (từ link) chưa có trong danh sách thì thêm vào cuối."""
        index = self.category.findData(category or "")
        if index < 0:
            self.category.addItem(watchcount.category_label(category), category)
            index = self.category.count() - 1
        self.category.setCurrentIndex(index)

    def _set_extra_params(self, params: dict) -> None:
        self._extra_params = dict(params or {})
        text = ", ".join(f"{k}={v}" for k, v in sorted(self._extra_params.items()))
        self.extra_label.setText(text)
        self.extra_label.setToolTip("Các bộ lọc tool chưa có ô riêng, lấy từ link dán vào và gửi kèm khi quét")
        self.extra_caption.setVisible(bool(text))
        self.extra_host.setVisible(bool(text))

    # ---- dán link watchcount ----------------------------------------------------------------

    def apply_link(self) -> None:
        try:
            parsed = watchcount.parse_search_url(self.link_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Link watchcount", str(exc))
            return
        box = self.link_confirm_box(parsed)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self.apply_parsed_link(parsed, clear_filters=box.checkBox().isChecked())
        self.link_input.clear()
        self.link_applied.emit(parsed["keyword"])

    def link_confirm_box(self, parsed: dict) -> QMessageBox:
        low, high = parsed["min_price"], parsed["max_price"]
        price = " ".join(part for part in (f"từ ${low:g}" if low else "", f"đến ${high:g}" if high else "") if part)

        lines = [f"• Từ khoá: {parsed['keyword'] or '(không có)'}"
                 + (" — thêm vào danh sách Từ khoá" if parsed["keyword"] else ""),
                 f"• Tab tìm kiếm: {watchcount.STATUS_OPTIONS[parsed['status']]}"]
        if parsed["status"] == "sold":
            lines.append(f"• Có đơn trong vòng: {watchcount.LAST_SOLD_OPTIONS[parsed['last_sold_within']]}")
        lines += [f"• eBay site: {parsed['site']}",
                  f"• Danh mục: {watchcount.category_label(parsed['category'])}",
                  f"• Sắp xếp: {watchcount.SORT_OPTIONS[parsed['sort_by']].split(' (')[0]}",
                  f"• Loại listing: {watchcount.LISTING_TYPES[parsed['listing_type']]}",
                  f"• Tình trạng: {watchcount.CONDITIONS[parsed['condition']]}",
                  f"• Giá: {price or 'không lọc'}",
                  f"• Exact Match Keywords: {'có' if parsed['exact_match'] else 'không'}"]
        if parsed["start_age_days"] is not None:
            lines.append(f"• Bộ lọc Start <= {parsed['start_age_days']:g} ngày (Newly Listed Within)")
        if parsed["extra_params"]:
            lines.append("• Tham số thêm: " + ", ".join(f"{k}={v}" for k, v in sorted(parsed["extra_params"].items())))
        lines += [f"⚠ {note}" for note in parsed["notes"]]

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Áp dụng link watchcount")
        box.setText("Tool sẽ đổi cài đặt quét như sau rồi lưu lại:")
        box.setInformativeText("\n".join(lines) + "\n\nCài đặt này dùng chung cho mọi từ khoá đang bật và cho lịch quét.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        # ô tích phải có parent là hộp thoại, không thì Python giải phóng nó ngay và app crash khi đọc lại
        clear_box = QCheckBox("Xoá trống Bộ lọc khi quét để ra đủ sản phẩm như trên web (nên chọn)", box)
        clear_box.setChecked(True)
        box.setCheckBox(clear_box)
        return box

    def apply_parsed_link(self, parsed: dict, clear_filters: bool) -> None:
        self.status.setCurrentIndex(max(0, self.status.findData(parsed["status"])))
        self._fill_sorts(parsed["sort_by"])
        self.last_sold.setCurrentIndex(max(0, self.last_sold.findData(parsed["last_sold_within"])))
        self.site.setCurrentText(parsed["site"])
        self._set_category(parsed["category"])
        self.listing_type.setCurrentIndex(max(0, self.listing_type.findData(parsed["listing_type"])))
        self.condition.setCurrentIndex(max(0, self.condition.findData(parsed["condition"])))
        self.min_price.setValue(parsed["min_price"] or 0)
        self.max_price.setValue(parsed["max_price"] or 0)
        self.exact_match.setChecked(parsed["exact_match"])
        self._set_extra_params(parsed["extra_params"])
        rules = self.filter_editor.rule_dicts()
        for rule in rules:
            if clear_filters:
                rule["value"] = None
            if rule["field"] == "start_age_days" and parsed["start_age_days"] is not None:
                rule["op"], rule["value"] = "<=", parsed["start_age_days"]
        self.filter_editor.set_rules(rules)

    def load_from_config(self) -> None:
        s = self.cfg["search"]
        self.status.setCurrentIndex(max(0, self.status.findData(s.get("status", "sold"))))
        self.last_sold.setCurrentIndex(max(0, self.last_sold.findData(s.get("last_sold_within") or "")))
        self._fill_sorts(s["sort_by"])
        self.site.setCurrentText(s["site"])
        self.listing_type.setCurrentIndex(max(0, self.listing_type.findData(s["listing_type"])))
        self.condition.setCurrentIndex(max(0, self.condition.findData(s.get("condition") or "")))
        self._set_category(s.get("category") or "")
        self.min_price.setValue(float(s.get("min_price") or 0))
        self.max_price.setValue(float(s.get("max_price") or 0))
        self.exact_match.setChecked(bool(s.get("exact_match")))
        self._set_extra_params(s.get("extra_params") or {})
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
        s["status"] = self.status.currentData()
        s["last_sold_within"] = self.last_sold.currentData()
        s["site"] = self.site.currentText()
        s["sort_by"] = self.sort_by.currentData()
        s["listing_type"] = self.listing_type.currentData()
        s["condition"] = self.condition.currentData()
        s["category"] = self.category.currentData()
        low, high = _price_value(self.min_price), _price_value(self.max_price)
        if low and high and low > high:
            low, high = high, low
        s["min_price"], s["max_price"] = low, high
        s["exact_match"] = self.exact_match.isChecked()
        s["extra_params"] = dict(self._extra_params)
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
