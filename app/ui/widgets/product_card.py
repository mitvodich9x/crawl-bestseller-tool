from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.core.filters import field_value

CARD_WIDTH = 250
IMAGE_SIZE = 226


def _fmt_age(days: float | None) -> str:
    if days is None:
        return "—"
    if days < 1:
        return f"{max(1, round(days * 24))} giờ trước"
    return f"{days:.0f} ngày trước"


class ProductCard(QFrame):
    def __init__(self, product: dict, parent=None):
        super().__init__(parent)
        self.product = product
        self.setObjectName("productCard")
        self.setFixedWidth(CARD_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.image = QLabel("Đang tải ảnh...")
        self.image.setObjectName("cardImage")
        self.image.setFixedSize(IMAGE_SIZE, IMAGE_SIZE)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setCursor(Qt.CursorShape.PointingHandCursor)
        self.image.mousePressEvent = lambda _e: self._open_ebay()
        layout.addWidget(self.image)

        keyword = QLabel(product.get("keyword") or "")
        keyword.setObjectName("keywordChip")
        keyword.setWordWrap(True)
        layout.addWidget(keyword)

        title = QLabel(product.get("title") or "")
        title.setObjectName("cardTitle")
        title.setWordWrap(True)
        title.setFixedHeight(54)
        title.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        title.setToolTip(product.get("title") or "")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title)

        stats = QGridLayout()
        stats.setHorizontalSpacing(8)
        stats.setVerticalSpacing(2)
        days_per_sale = product.get("days_per_sale")
        rows = [
            ("Tổng đơn", f"{product.get('total_sold') or 0}"),
            ("Sell one", product.get("one_unit_every") or "—"),
            ("1 đơn / ngày", f"{days_per_sale:.1f} ngày" if days_per_sale else "—"),
            ("Start", _fmt_age(field_value(product, "start_age_days"))),
            ("Theo dõi", f"{product.get('watchers') or 0}"),
            ("Giá", product.get("price_text") or "—"),
        ]
        for i, (label, value) in enumerate(rows):
            name = QLabel(label)
            name.setObjectName("statLabel")
            val = QLabel(value)
            val.setObjectName("statValue")
            stats.addWidget(name, i // 2 * 2, i % 2)
            stats.addWidget(val, i // 2 * 2 + 1, i % 2)
        layout.addLayout(stats)

        buttons = QHBoxLayout()
        open_btn = QPushButton("Mở eBay")
        open_btn.clicked.connect(self._open_ebay)
        copy_btn = QPushButton("Copy tiêu đề")
        copy_btn.clicked.connect(lambda: QGuiApplication.clipboard().setText(product.get("title") or ""))
        img_btn = QPushButton("Copy ảnh")
        img_btn.setToolTip("Copy link ảnh")
        img_btn.clicked.connect(lambda: QGuiApplication.clipboard().setText(product.get("image_url") or ""))
        for btn in (open_btn, copy_btn, img_btn):
            btn.setObjectName("cardButton")
            buttons.addWidget(btn)
        layout.addLayout(buttons)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.image.setPixmap(pixmap.scaled(IMAGE_SIZE, IMAGE_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))

    def _open_ebay(self) -> None:
        if self.product.get("item_url"):
            QDesktopServices.openUrl(QUrl(self.product["item_url"]))
