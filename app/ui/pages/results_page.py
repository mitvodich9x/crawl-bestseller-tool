"""Trang Kết quả: Bảng 1 = mọi sản phẩm cào về (gộp theo từ khoá), Bảng 2 = sản phẩm đạt Bộ lọc khi quét."""
import html
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QShowEvent
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from app.core import filters
from app.core.results import keyword_summary, merge_keywords
from app.db.database import Database
from app.export.excel import export_tables
from app.ui.fmt import local_time
from app.ui.widgets.filter_editor import FilterEditor
from app.ui.widgets.flow_layout import FlowLayout
from app.ui.widgets.image_loader import ImageLoader
from app.ui.widgets.product_card import ProductCard

PAGE_SIZE = 60
SUMMARY_MAX_KEYWORDS = 12

TAB_ALL = "Bảng 1 · Tất cả SP cào về"
TAB_KEPT = "Bảng 2 · SP đạt bộ lọc"
SHEET_ALL = "1. Cào về"
SHEET_KEPT = "2. Đạt bộ lọc"
EMPTY_DB = ("Chưa có sản phẩm nào được cào về cho lựa chọn này.\n"
            "Thêm từ khoá rồi bấm ▶ Quét ngay, hoặc chọn Từ khoá / Lần quét khác.")
EMPTY_SEARCH = "Không có sản phẩm nào khớp ô tìm kiếm / Bộ lọc nâng cao."

SORTS = {
    "Tổng đơn cao nhất": lambda p: -(p.get("total_sold") or 0),
    "Bán nhanh nhất (sell one)": lambda p: p.get("days_per_sale") if p.get("days_per_sale") else float("inf"),
    "Mới đăng nhất": lambda p: -(datetime.fromisoformat(p["start_time"]).timestamp() if p.get("start_time") else 0),
    "Bán gần đây nhất": lambda p: -(datetime.fromisoformat(p["last_sold_at"]).timestamp()
                                    if p.get("last_sold_at") else 0),
    "Theo dõi nhiều nhất": lambda p: -(p.get("watchers") or 0),
    "Mới thấy gần đây": lambda p: -(datetime.fromisoformat(p["last_seen"]).timestamp() if p.get("last_seen") else 0),
}


class ProductGrid(QWidget):
    """Một bảng kết quả: lưới thẻ sản phẩm + phân trang.

    Chỉ dựng thẻ khi bảng đang hiện; bảng ở tab còn lại dựng lúc được mở, nên đổi bộ lọc không tốn gấp đôi.
    """

    def __init__(self, loader: ImageLoader, parent=None):
        super().__init__(parent)
        self.loader = loader
        self._items: list[dict] = []
        self._page = 0
        self._empty_text = EMPTY_DB
        self._dirty = True
        self._cards_by_url: dict[str, list[ProductCard]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 8, 4, 4)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = FlowLayout(self.grid_host)
        self.scroll.setWidget(self.grid_host)
        root.addWidget(self.scroll, 1)

        pager = QHBoxLayout()
        self.prev_btn = QPushButton("‹ Trang trước")
        self.next_btn = QPushButton("Trang sau ›")
        self.page_label = QLabel()
        pager.addStretch(1)
        pager.addWidget(self.prev_btn)
        pager.addWidget(self.page_label)
        pager.addWidget(self.next_btn)
        pager.addStretch(1)
        root.addLayout(pager)

        self.prev_btn.clicked.connect(lambda: self.go_page(self._page - 1))
        self.next_btn.clicked.connect(lambda: self.go_page(self._page + 1))
        self.loader.loaded.connect(self._on_image)

    @property
    def items(self) -> list[dict]:
        return self._items

    def set_items(self, items: list[dict], empty_text: str) -> None:
        self._items = items
        self._empty_text = empty_text
        self._page = 0
        self._dirty = True
        if self.isVisible():
            self._render()

    def go_page(self, page: int) -> None:
        self._page = page
        self._render()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._dirty:
            self._render()

    def _render(self) -> None:
        self._dirty = False
        pages = max(1, -(-len(self._items) // PAGE_SIZE))
        self._page = min(max(0, self._page), pages - 1)
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < pages - 1)
        self.page_label.setText(f"Trang {self._page + 1}/{pages}")

        self.grid.clear()
        self._cards_by_url.clear()
        start = self._page * PAGE_SIZE
        for product in self._items[start:start + PAGE_SIZE]:
            card = ProductCard(product)
            self.grid.addWidget(card)
            url = product.get("image_url")
            if url:
                self._cards_by_url.setdefault(url, []).append(card)
                cached = self.loader.cached(url)
                if cached is not None:
                    card.set_pixmap(cached)
                else:
                    self.loader.request(url)
        if not self._items:
            empty = QLabel(self._empty_text)
            empty.setObjectName("emptyLabel")
            self.grid.addWidget(empty)
        self.scroll.verticalScrollBar().setValue(0)

    def _on_image(self, url: str, pixmap: QPixmap) -> None:
        for card in self._cards_by_url.get(url, []):
            card.set_pixmap(pixmap)


class ResultsPage(QWidget):
    results_changed = pyqtSignal()  # đã xoá kết quả: lịch sử lần quét ở trang Nhật ký cần nạp lại

    def __init__(self, db: Database, get_scan_rules, is_busy=lambda: False, parent=None):
        super().__init__(parent)
        self.db = db
        self.get_scan_rules = get_scan_rules
        self.is_busy = is_busy  # đang quét thì không cho xoá kết quả
        self._rows: list[dict] = []  # dòng (sản phẩm × từ khoá) theo lựa chọn Từ khoá / Lần quét
        self._all: list[dict] = []  # mỗi sản phẩm một thẻ
        self._shown: list[dict] = []  # Bảng 1 sau ô tìm kiếm, bộ lọc nâng cao, sắp xếp
        self._kept: list[dict] = []  # Bảng 2: phần của Bảng 1 đạt Bộ lọc khi quét
        self.loader = ImageLoader(self)

        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.keyword_combo = QComboBox()
        self.keyword_combo.setMinimumWidth(180)
        self.run_combo = QComboBox()
        self.run_combo.setMinimumWidth(220)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(list(SORTS))
        for label, widget in (("Từ khoá", self.keyword_combo), ("Lần quét", self.run_combo),
                              ("Sắp xếp", self.sort_combo)):
            bar.addWidget(QLabel(label))
            bar.addWidget(widget)
        bar.addStretch(1)
        root.addLayout(bar)

        bar2 = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Tìm trong tiêu đề...")
        self.search_box.setMinimumWidth(260)
        bar2.addWidget(self.search_box)
        self.toggle_filter_btn = QPushButton("Bộ lọc nâng cao ▾")
        self.toggle_filter_btn.setCheckable(True)
        self.use_scan_rules_btn = QPushButton("Lấy bộ lọc đang dùng khi quét")
        refresh_btn = QPushButton("Làm mới")
        self.delete_btn = QPushButton("🗑 Xoá kết quả")
        self.delete_btn.setToolTip("Xoá kết quả đang xem (theo Từ khoá / Lần quét đang chọn; chọn Tất cả thì xoá hết). "
                                   "Danh sách từ khoá và cài đặt giữ nguyên.")
        export_btn = QPushButton("Xuất Excel")
        export_btn.setObjectName("primaryButton")
        export_btn.setToolTip("Xuất 2 sheet: 1. Cào về (Bảng 1) và 2. Đạt bộ lọc (Bảng 2)")
        bar2.addWidget(self.toggle_filter_btn)
        bar2.addWidget(self.use_scan_rules_btn)
        bar2.addStretch(1)
        bar2.addWidget(refresh_btn)
        bar2.addWidget(self.delete_btn)
        bar2.addWidget(export_btn)
        root.addLayout(bar2)

        self.filter_panel = QFrame()
        self.filter_panel.setObjectName("panel")
        panel_layout = QVBoxLayout(self.filter_panel)
        self.filter_editor = FilterEditor()
        panel_layout.addWidget(self.filter_editor)
        self.filter_panel.setVisible(False)
        root.addWidget(self.filter_panel)

        # mỗi từ khoá cào về bao nhiêu / đạt lọc bao nhiêu, để thấy ngay mọi từ khoá đều đã được quét
        self.summary_label = QLabel()
        self.summary_label.setObjectName("hint")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.summary_label)

        self.tabs = QTabWidget()
        self.grid_all = ProductGrid(self.loader)
        self.grid_kept = ProductGrid(self.loader)
        self.tabs.addTab(self.grid_all, TAB_ALL)
        self.tabs.addTab(self.grid_kept, TAB_KEPT)
        self.tabs.setTabToolTip(0, "Mọi sản phẩm tool tải về từ watchcount cho các từ khoá, chưa qua Bộ lọc khi quét")
        self.tabs.setTabToolTip(1, "Chỉ sản phẩm đạt Bộ lọc khi quét (Cài đặt quét → Bộ lọc khi quét)")
        root.addWidget(self.tabs, 1)

        self._debounce = QTimer(self, singleShot=True, interval=300)
        self._debounce.timeout.connect(self._apply_filters)

        self.keyword_combo.currentIndexChanged.connect(self.reload)
        self.run_combo.currentIndexChanged.connect(self.reload)
        self.sort_combo.currentIndexChanged.connect(self._apply_filters)
        self.search_box.textChanged.connect(self._debounce.start)
        self.filter_editor.changed.connect(self._debounce.start)
        self.toggle_filter_btn.toggled.connect(self._toggle_filter_panel)
        self.use_scan_rules_btn.clicked.connect(lambda: self.filter_editor.set_rules(self.get_scan_rules()))
        refresh_btn.clicked.connect(self.refresh)
        self.delete_btn.clicked.connect(self._delete)
        export_btn.clicked.connect(self._export)

        self.filter_editor.set_rules([])
        self.refresh()

    def _toggle_filter_panel(self, on: bool) -> None:
        self.filter_panel.setVisible(on)
        self.toggle_filter_btn.setText("Bộ lọc nâng cao ▴" if on else "Bộ lọc nâng cao ▾")

    # ---- data -----------------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload the combo choices (keywords, runs) and then the products."""
        current_kw = self.keyword_combo.currentData()
        current_run = self.run_combo.currentData()
        for combo in (self.keyword_combo, self.run_combo):
            combo.blockSignals(True)
            combo.clear()
        self.keyword_combo.addItem("Tất cả", None)
        for kw in self.db.keywords_with_products():
            self.keyword_combo.addItem(kw, kw)
        self.run_combo.addItem("Tất cả lần quét", None)
        for run in self.db.list_runs(30):
            self.run_combo.addItem(f"#{run['id']} {local_time(run['started_at'])} — {run['total_found']} SP, "
                                   f"{run['total_kept']} đạt lọc", run["id"])
        for combo, value in ((self.keyword_combo, current_kw), (self.run_combo, current_run)):
            index = combo.findData(value)
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
        self.reload()

    def reload(self) -> None:
        keyword, run_id = self.keyword_combo.currentData(), self.run_combo.currentData()
        self._rows = self.db.query_products(keyword=keyword, run_id=run_id)
        self._all = merge_keywords(self._rows)
        # xem tất cả thì liệt kê cả từ khoá đang bật mà chưa có sản phẩm nào
        enabled = [k["keyword"] for k in self.db.list_keywords(enabled_only=True)] if not (keyword or run_id) else []
        self._show_summary(keyword_summary(self._rows, enabled))
        self._apply_filters()

    def _show_summary(self, entries: list[tuple[str, int, int]]) -> None:
        if not entries:
            self.summary_label.setVisible(False)
            return
        parts = [f"<b>{html.escape(name)}</b>: {found} cào về, {kept} đạt lọc"
                 for name, found, kept in entries[:SUMMARY_MAX_KEYWORDS]]
        if len(entries) > SUMMARY_MAX_KEYWORDS:
            parts.append(f"… và {len(entries) - SUMMARY_MAX_KEYWORDS} từ khoá khác")
        self.summary_label.setText("Theo từ khoá — " + " &nbsp;·&nbsp; ".join(parts))
        self.summary_label.setVisible(True)

    def _apply_filters(self) -> None:
        text = self.search_box.text().strip().lower()
        shown = filters.apply(self._all, self.filter_editor.rules())
        if text:
            shown = [p for p in shown if text in (p.get("title") or "").lower()]
        shown.sort(key=SORTS[self.sort_combo.currentText()])
        kept = [p for p in shown if p.get("kept")]
        self._shown, self._kept = shown, kept

        if not self._all:
            empty_all = empty_kept = EMPTY_DB
        else:
            empty_all = EMPTY_SEARCH
            empty_kept = EMPTY_SEARCH if not shown else (
                f"Có {len(shown)} sản phẩm cào về (xem Bảng 1) nhưng không sản phẩm nào đạt Bộ lọc khi quét.\n"
                "Nới bộ lọc ở Cài đặt quét → Bộ lọc khi quét rồi quét lại, hoặc lọc Bảng 1 bằng Bộ lọc nâng cao.")
        self.tabs.setTabText(0, f"{TAB_ALL} ({len(shown)})")
        self.tabs.setTabText(1, f"{TAB_KEPT} ({len(kept)})")
        self.grid_all.set_items(shown, empty_all)
        self.grid_kept.set_items(kept, empty_kept)

    # ---- actions --------------------------------------------------------------------------

    def _delete(self) -> None:
        if self.is_busy():
            QMessageBox.information(self, "Xoá kết quả", "Đang quét hoặc đang dùng trình duyệt, hãy chờ xong rồi xoá.")
            return
        if not self._all:
            QMessageBox.information(self, "Xoá kết quả", "Không có kết quả nào để xoá với lựa chọn hiện tại.")
            return
        keyword, run_id = self.keyword_combo.currentData(), self.run_combo.currentData()
        if keyword and run_id:
            target = f"kết quả của từ khoá \"{keyword}\" trong lần quét #{run_id}"
        elif keyword:
            target = f"toàn bộ kết quả đã cào của từ khoá \"{keyword}\""
        elif run_id:
            target = f"kết quả của lần quét #{run_id} (lần quét này cũng bị xoá khỏi lịch sử)"
        else:
            target = "TOÀN BỘ kết quả đã cào (mọi từ khoá, mọi lần quét)"
        count = len(self._all)
        answer = QMessageBox.question(
            self, "Xoá kết quả",
            f"Xoá {target}?\n\n{count} sản phẩm sẽ bị xoá khỏi trang Kết quả, không hoàn tác được.\n"
            "Danh sách Từ khoá và Cài đặt quét giữ nguyên.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_results(keyword=keyword, run_id=run_id)
        self.refresh()
        self.results_changed.emit()
        QMessageBox.information(self, "Xoá kết quả", f"Đã xoá {count} sản phẩm khỏi kết quả.")

    def _export(self) -> None:
        if not self._shown:
            QMessageBox.information(self, "Xuất Excel", "Không có sản phẩm nào để xuất.")
            return
        default = f"bestseller_{datetime.now():%Y%m%d_%H%M}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Xuất Excel", default, "Excel (*.xlsx)")
        if not path:
            return
        try:
            export_tables([(SHEET_ALL, self._shown), (SHEET_KEPT, self._kept)], path)
        except OSError as exc:
            QMessageBox.warning(self, "Xuất Excel", f"Không ghi được file (đang mở trong Excel?):\n{exc}")
            return
        QMessageBox.information(
            self, "Xuất Excel",
            f"Đã xuất 2 sheet:\n• {SHEET_ALL}: {len(self._shown)} sản phẩm\n"
            f"• {SHEET_KEPT}: {len(self._kept)} sản phẩm\n\n{path}")
