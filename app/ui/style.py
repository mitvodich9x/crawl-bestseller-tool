from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

STYLESHEET = """
QWidget { font-size: 13px; color: #1f2937; }
QMainWindow, #contentArea { background: #f3f5f9; }
#sidebar { background: #1f3a5f; border: none; }
#sidebar::item { color: #dbe4f0; padding: 12px 16px; border-radius: 6px; margin: 2px 8px; }
#sidebar::item:selected { background: #2f5b8f; color: white; }
#sidebar::item:hover:!selected { background: #28496f; }
#appTitle { color: white; font-size: 16px; font-weight: 700; padding: 16px; background: #1f3a5f; }
#topBar { background: white; border-bottom: 1px solid #e3e7ee; }
QPushButton { background: white; border: 1px solid #c9d2de; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { background: #eef3f9; }
QPushButton:disabled { color: #9aa5b4; background: #f3f5f9; }
#primaryButton { background: #2563eb; color: white; border: 1px solid #2563eb; font-weight: 600; }
#primaryButton:hover { background: #1d4ed8; }
#primaryButton:disabled { background: #93b4f5; border-color: #93b4f5; }
#dangerButton { background: #dc2626; color: white; border: 1px solid #dc2626; font-weight: 600; }
#dangerButton:disabled { background: #f1a5a5; border-color: #f1a5a5; }
QGroupBox { background: white; border: 1px solid #e3e7ee; border-radius: 8px; margin-top: 14px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; font-weight: 700; }
#panel { background: white; border: 1px solid #e3e7ee; border-radius: 8px; }
#hint { color: #6b7280; font-size: 12px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QPlainTextEdit {
    background: white; border: 1px solid #c9d2de; border-radius: 5px; padding: 4px 6px; }
#productCard { background: white; border: 1px solid #e3e7ee; border-radius: 10px; }
#productCard:hover { border: 1px solid #2563eb; }
#cardImage { background: #f3f5f9; border-radius: 6px; color: #9aa5b4; }
#cardTitle { font-weight: 600; }
#keywordChip { color: #1d4ed8; background: #e8effd; border-radius: 4px; padding: 2px 6px; font-size: 11px; }
#statLabel { color: #6b7280; font-size: 11px; }
#statValue { font-weight: 600; }
#cardButton { padding: 4px 6px; font-size: 11px; }
#emptyLabel { color: #6b7280; font-size: 15px; padding: 40px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
"""


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#2563eb"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Segoe UI", 30, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "B")
    painter.end()
    return QIcon(pixmap)
