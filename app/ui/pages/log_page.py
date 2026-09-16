from datetime import datetime

from PyQt6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel, QPlainTextEdit, QSplitter, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt

from app.db.database import Database
from app.ui.fmt import local_time

STATUS_LABELS = {
    "running": "Đang chạy",
    "completed": "Hoàn tất",
    "stopped": "Đã dừng",
    "failed": "Lỗi",
    "need_login": "Cần đăng nhập",
    "blocked": "Bị chặn",
    "quota_exhausted": "Hết lượt",
}


class LogPage(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        root = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(5000)
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(QLabel("Nhật ký"))
        top_layout.addWidget(self.text)
        splitter.addWidget(top)

        self.runs = QTableWidget(0, 7)
        self.runs.setHorizontalHeaderLabels(["#", "Bắt đầu", "Kết thúc", "Kích hoạt", "Trạng thái",
                                             "SP tìm thấy / đạt lọc", "Lượt dùng"])
        self.runs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.runs.horizontalHeader().setStretchLastSection(True)
        self.runs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs.verticalHeader().setVisible(False)
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(QLabel("Lịch sử các lần quét"))
        bottom_layout.addWidget(self.runs)
        splitter.addWidget(bottom)
        splitter.setSizes([400, 250])
        root.addWidget(splitter)
        self.reload_runs()

    def append(self, message: str) -> None:
        self.text.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")

    def reload_runs(self) -> None:
        rows = self.db.list_runs(100)
        self.runs.setRowCount(len(rows))
        for i, run in enumerate(rows):
            values = [
                run["id"],
                local_time(run["started_at"], "%d/%m/%Y %H:%M:%S"),
                local_time(run["finished_at"], "%H:%M:%S"),
                {"manual": "Thủ công", "schedule": "Theo lịch"}.get(run["trigger"], run["trigger"]),
                STATUS_LABELS.get(run["status"], run["status"]) + (f" — {run['error']}" if run["error"] else ""),
                f"{run['total_found']} / {run['total_kept']}",
                run["pages_used"],
            ]
            for col, value in enumerate(values):
                self.runs.setItem(i, col, QTableWidgetItem(str(value)))
