from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from app.core import filters
from app.db.database import Database
from app.export.excel import export_products
from app.ui.fmt import local_time
from app.ui.widgets.filter_editor import FilterEditor
from app.ui.widgets.flow_layout import FlowLayout
from app.ui.widgets.image_loader import ImageLoader
from app.ui.widgets.product_card import ProductCard

PAGE_SIZE = 60

SORTS = {
    "Tổng đơn cao nhất": lambda p: -(p.get("total_sold") or 0),
    "Bán nhanh nhất (sell one)": lambda p: p.get("days_per_sale") if p.get("days_per_sale") else float("inf"),
    "Mới đăng nhất": lambda p: -(datetime.fromisoformat(p["start_time"]).timestamp() if p.get("start_time") else 0),
    "Theo dõi nhiều nhất": lambda p: -(p.get("watchers") or 0),
    "Mới thấy gần đây": lambda p: -(datetime.fromisoformat(p["last_seen"]).timestamp() if p.get("last_seen") else 0),
}


def _merge_keywords(rows: list[dict]) -> list[dict]:
    """A product found by several keywords becomes one card listing all of them."""
    merged: dict[str, dict] = {}
    for row in rows:
        existing = merged.get(row["item_id"])
        if existing is None:
            merged[row["item_id"]] = dict(row)
        elif row["keyword"].lower() not in existing["keyword"].lower().split(", "):
            existing["keyword"] += ", " + row["keyword"]
    return list(merged.values())


class ResultsPage(QWidget):
    def __init__(self, db: Database, get_scan_rules, parent=None):
        super().__init__(parent)
        self.db = db
        self.get_scan_rules = get_scan_rules
        self._all: list[dict] = []
        self._filtered: list[dict] = []
        self._page = 0
        self._cards_by_url: dict[str, list[ProductCard]] = {}
        self.loader = ImageLoader(self)
        self.loader.loaded.connect(self._on_image)

        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.keyword_combo = QComboBox()
        self.keyword_combo.setMinimumWidth(180)
        self.run_combo = QComboBox()
        self.run_combo.setMinimumWidth(220)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(list(SORTS))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Tìm trong tiêu đề...")
        self.kept_only = QCheckBox("Chỉ SP đạt bộ lọc khi quét")
        self.kept_only.setChecked(True)
        for label, widget in (("Từ khoá", self.keyword_combo), ("Lần quét", self.run_combo),
                              ("Sắp xếp", self.sort_combo)):
            bar.addWidget(QLabel(label))
            bar.addWidget(widget)
        bar.addWidget(self.kept_only)
        bar.addStretch(1)
        root.addLayout(bar)

        bar2 = QHBoxLayout()
        self.search_box.setMinimumWidth(260)
        bar2.addWidget(self.search_box)
        self.toggle_filter_btn = QPushButton("Bộ lọc nâng cao ▾")
        self.toggle_filter_btn.setCheckable(True)
        self.use_scan_rules_btn = QPushButton("Lấy bộ lọc đang dùng khi quét")
        refresh_btn = QPushButton("Làm mới")
        export_btn = QPushButton("Xuất Excel")
        export_btn.setObjectName("primaryButton")
        self.count_label = QLabel()
        bar2.addWidget(self.toggle_filter_btn)
        bar2.addWidget(self.use_scan_rules_btn)
        bar2.addStretch(1)
        bar2.addWidget(self.count_label)
        bar2.addWidget(refresh_btn)
        bar2.addWidget(export_btn)
        root.addLayout(bar2)

        self.filter_panel = QFrame()
        self.filter_panel.setObjectName("panel")
        panel_layout = QVBoxLayout(self.filter_panel)
        self.filter_editor = FilterEditor()
        panel_layout.addWidget(self.filter_editor)
        self.filter_panel.setVisible(False)
        root.addWidget(self.filter_panel)

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

        self._debounce = QTimer(self, singleShot=True, interval=300)
        self._debounce.timeout.connect(self._apply_filters)

        self.keyword_combo.currentIndexChanged.connect(self.reload)
        self.run_combo.currentIndexChanged.connect(self.reload)
        self.kept_only.toggled.connect(self.reload)
        self.sort_combo.currentIndexChanged.connect(self._apply_filters)
        self.search_box.textChanged.connect(self._debounce.start)
        self.filter_editor.changed.connect(self._debounce.start)
        self.toggle_filter_btn.toggled.connect(self._toggle_filter_panel)
        self.use_scan_rules_btn.clicked.connect(lambda: self.filter_editor.set_rules(self.get_scan_rules()))
        refresh_btn.clicked.connect(self.refresh)
        export_btn.clicked.connect(self._export)
        self.prev_btn.clicked.connect(lambda: self._go_page(self._page - 1))
        self.next_btn.clicked.connect(lambda: self._go_page(self._page + 1))

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
            self.run_combo.addItem(f"#{run['id']} {local_time(run['started_at'])} — {run['total_kept']} SP đạt lọc",
                                   run["id"])
        for combo, value in ((self.keyword_combo, current_kw), (self.run_combo, current_run)):
            index = combo.findData(value)
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
        self.reload()

    def reload(self) -> None:
        rows = self.db.query_products(keyword=self.keyword_combo.currentData(), run_id=self.run_combo.currentData(),
                                      kept_only=self.kept_only.isChecked())
        self._all = _merge_keywords(rows)
        self._apply_filters()

    def _apply_filters(self) -> None:
        text = self.search_box.text().strip().lower()
        items = filters.apply(self._all, self.filter_editor.rules())
        if text:
            items = [p for p in items if text in (p.get("title") or "").lower()]
        items.sort(key=SORTS[self.sort_combo.currentText()])
        self._filtered = items
        self.count_label.setText(f"{len(items)} sản phẩm")
        self._go_page(0)

    # ---- rendering ------------------------------------------------------------------------

    def _go_page(self, page: int) -> None:
        pages = max(1, -(-len(self._filtered) // PAGE_SIZE))
        self._page = min(max(0, page), pages - 1)
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < pages - 1)
        self.page_label.setText(f"Trang {self._page + 1}/{pages}")

        self.grid.clear()
        self._cards_by_url.clear()
        start = self._page * PAGE_SIZE
        for product in self._filtered[start:start + PAGE_SIZE]:
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
        if not self._filtered:
            empty = QLabel("Chưa có sản phẩm. Thêm từ khoá rồi bấm \"Quét ngay\".")
            empty.setObjectName("emptyLabel")
            self.grid.addWidget(empty)
        self.scroll.verticalScrollBar().setValue(0)

    def _on_image(self, url: str, pixmap: QPixmap) -> None:
        for card in self._cards_by_url.get(url, []):
            card.set_pixmap(pixmap)

    def _export(self) -> None:
        if not self._filtered:
            QMessageBox.information(self, "Xuất Excel", "Không có sản phẩm nào để xuất.")
            return
        default = f"bestseller_{datetime.now():%Y%m%d_%H%M}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Xuất Excel", default, "Excel (*.xlsx)")
        if not path:
            return
        try:
            export_products(self._filtered, path)
        except OSError as exc:
            QMessageBox.warning(self, "Xuất Excel", f"Không ghi được file (đang mở trong Excel?):\n{exc}")
            return
        QMessageBox.information(self, "Xuất Excel", f"Đã xuất {len(self._filtered)} sản phẩm:\n{path}")
