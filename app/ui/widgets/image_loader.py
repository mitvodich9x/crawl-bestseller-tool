"""Async image loading on the UI thread via QNetworkAccessManager, with memory + disk cache."""
from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkReply, QNetworkRequest

from app.paths import image_cache_dir

_MEMORY_LIMIT = 600


class ImageLoader(QObject):
    loaded = pyqtSignal(str, QPixmap)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self)
        cache.setCacheDirectory(str(image_cache_dir()))
        cache.setMaximumCacheSize(500 * 1024 * 1024)
        self._manager.setCache(cache)
        self._memory: dict[str, QPixmap] = {}
        self._pending: set[str] = set()

    def cached(self, url: str) -> QPixmap | None:
        return self._memory.get(url)

    def request(self, url: str | None) -> None:
        if not url or url in self._memory or url in self._pending:
            if url in self._memory:
                self.loaded.emit(url, self._memory[url])
            return
        self._pending.add(url)
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                         QNetworkRequest.CacheLoadControl.PreferCache)
        reply = self._manager.get(req)
        reply.finished.connect(lambda r=reply, u=url: self._on_finished(r, u))

    def _on_finished(self, reply: QNetworkReply, url: str) -> None:
        self._pending.discard(url)
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            pixmap = QPixmap()
            if pixmap.loadFromData(bytes(reply.readAll())):
                if len(self._memory) >= _MEMORY_LIMIT:
                    self._memory.pop(next(iter(self._memory)))
                self._memory[url] = pixmap
                self.loaded.emit(url, pixmap)
        finally:
            reply.deleteLater()
