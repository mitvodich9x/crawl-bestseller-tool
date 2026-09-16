from datetime import date, datetime

from PyQt6.QtCore import QDate, QTime, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QDateEdit, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSpinBox,
                             QTimeEdit, QVBoxLayout, QWidget)

from app.core import scheduler


class SchedulePage(QWidget):
    save_requested = pyqtSignal()

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        root = QVBoxLayout(self)

        box = QGroupBox("Lịch quét tự động")
        form = QFormLayout(box)
        self.mode = QComboBox()
        for key, label in scheduler.MODES.items():
            self.mode.addItem(label, key)
        self.n_days = QSpinBox(minimum=1, maximum=60, suffix=" ngày")
        self.anchor = QDateEdit(calendarPopup=True)
        self.anchor.setDisplayFormat("dd/MM/yyyy")
        self.run_time = QTimeEdit()
        self.run_time.setDisplayFormat("HH:mm")
        form.addRow("Chế độ", self.mode)
        form.addRow("Lặp lại mỗi", self.n_days)
        form.addRow("Tính từ ngày", self.anchor)
        form.addRow("Giờ quét", self.run_time)
        root.addWidget(box)

        status = QGroupBox("Trạng thái")
        status_layout = QVBoxLayout(status)
        self.last_label = QLabel()
        self.next_label = QLabel()
        hint = QLabel("App phải đang chạy (có thể thu nhỏ dưới khay hệ thống). Nếu máy tắt đúng giờ quét, "
                      "app sẽ quét bù một lần khi mở lại trong ngày đó.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        status_layout.addWidget(self.last_label)
        status_layout.addWidget(self.next_label)
        status_layout.addWidget(hint)
        root.addWidget(status)

        row = QHBoxLayout()
        row.addStretch(1)
        save_btn = QPushButton("Lưu lịch quét")
        save_btn.setObjectName("primaryButton")
        row.addWidget(save_btn)
        root.addLayout(row)
        root.addStretch(1)

        self.mode.currentIndexChanged.connect(self._sync_enabled)
        save_btn.clicked.connect(self.save_requested)
        self.load_from_config()

    def _sync_enabled(self) -> None:
        every_n = self.mode.currentData() == "every_n_days"
        self.n_days.setEnabled(every_n)
        self.anchor.setEnabled(every_n)
        self.run_time.setEnabled(self.mode.currentData() != "manual")

    def load_from_config(self) -> None:
        s = self.cfg["schedule"]
        self.mode.setCurrentIndex(max(0, self.mode.findData(s["mode"])))
        self.n_days.setValue(int(s.get("n_days") or 2))
        anchor = date.fromisoformat(s.get("anchor_date") or date.today().isoformat())
        self.anchor.setDate(QDate(anchor.year, anchor.month, anchor.day))
        t = scheduler.parse_time(s.get("time"))
        self.run_time.setTime(QTime(t.hour, t.minute))
        self._sync_enabled()
        self.refresh_status()

    def write_to_config(self) -> None:
        s = self.cfg["schedule"]
        s["mode"] = self.mode.currentData()
        s["n_days"] = self.n_days.value()
        s["anchor_date"] = self.anchor.date().toPyDate().isoformat()
        s["time"] = self.run_time.time().toString("HH:mm")

    def refresh_status(self) -> None:
        last = self.cfg["state"].get("last_run_date")
        self.last_label.setText(f"Lần quét theo lịch gần nhất: {last or 'chưa có'}")
        nxt = scheduler.next_run(datetime.now(), self.cfg["schedule"], last)
        self.next_label.setText(f"Lần quét kế tiếp: {nxt:%d/%m/%Y %H:%M}" if nxt else "Lần quét kế tiếp: không có (thủ công)")
