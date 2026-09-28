"""Trang Hướng dẫn: đọc app/assets/guide/guide.html, ảnh minh hoạ nằm cùng thư mục."""
import re

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QImage, QTextDocument
from PyQt6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from app.paths import guide_dir

_IMG_RE = re.compile(r'<img\s+src="([^"]+)"(?:\s+width="(\d+)")?\s*>')


class GuidePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.browser = QTextBrowser()
        self.browser.setObjectName("guideBrowser")
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_link)
        layout.addWidget(self.browser)

        page = guide_dir() / "guide.html"
        if page.exists():
            self.browser.setHtml(self._with_images(page.read_text(encoding="utf-8")))
        else:
            self.browser.setPlainText(f"Không tìm thấy file hướng dẫn: {page}")

    def _with_images(self, html: str) -> str:
        """QTextBrowser chỉ co chiều ngang của ảnh và co kiểu nhanh (mờ), nên tự co đúng tỉ lệ, mượt, nét trên màn hình HiDPI."""
        document = self.browser.document()
        ratio = max(1.0, self.devicePixelRatioF())

        def replace(match: re.Match) -> str:
            name, width = match.group(1), match.group(2)
            image = QImage(str(guide_dir() / name))
            if image.isNull():
                return match.group(0)
            target_w = min(int(width), image.width()) if width else image.width()
            target_h = round(image.height() * target_w / image.width())
            scaled = image.scaled(round(target_w * ratio), round(target_h * ratio),
                                  Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(ratio)
            document.addResource(QTextDocument.ResourceType.ImageResource.value, QUrl(name), scaled)
            return f'<img src="{name}" width="{target_w}" height="{target_h}">'

        return _IMG_RE.sub(replace, html)

    def _on_link(self, url: QUrl) -> None:
        if url.hasFragment() and not url.host():
            self.browser.scrollToAnchor(url.fragment())
        else:
            QDesktopServices.openUrl(url)
