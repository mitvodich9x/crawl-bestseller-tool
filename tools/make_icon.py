"""Render app_icon.ico from the same drawing the app uses for its window/tray icon."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtGui import QIcon  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.ui.style import app_icon  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "app_icon.ico"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    icon: QIcon = app_icon()
    pixmap = icon.pixmap(256, 256)
    if not pixmap.save(str(OUT), "ICO"):
        raise SystemExit("Không ghi được file .ico")
    print("Đã tạo", OUT, pixmap.size())
