from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app.db.database import Database


class KeywordsPage(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        root = QVBoxLayout(self)

        root.addWidget(QLabel("Thêm từ khoá (mỗi dòng một từ khoá):"))
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("funny shirt\ncat mug\nchristmas ornament")
        self.input.setFixedHeight(110)
        root.addWidget(self.input)

        add_row = QHBoxLayout()
        add_btn = QPushButton("Thêm từ khoá")
        add_btn.setObjectName("primaryButton")
        import_btn = QPushButton("Nhập từ file .txt")
        export_btn = QPushButton("Xuất ra file .txt")
        add_row.addWidget(add_btn)
        add_row.addWidget(import_btn)
        add_row.addWidget(export_btn)
        add_row.addStretch(1)
        root.addLayout(add_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Bật", "Từ khoá", "Ngày thêm"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.count_label = QLabel()
        enable_all = QPushButton("Bật tất cả")
        disable_all = QPushButton("Tắt tất cả")
        delete_btn = QPushButton("Xoá dòng đang chọn")
        bottom.addWidget(self.count_label)
        bottom.addStretch(1)
        for btn in (enable_all, disable_all, delete_btn):
            bottom.addWidget(btn)
        root.addLayout(bottom)

        add_btn.clicked.connect(self._add_from_input)
        import_btn.clicked.connect(self._import)
        export_btn.clicked.connect(self._export)
        enable_all.clicked.connect(lambda: self._set_all(True))
        disable_all.clicked.connect(lambda: self._set_all(False))
        delete_btn.clicked.connect(self._delete_selected)
        self.table.itemChanged.connect(self._on_item_changed)
        self.reload()

    def reload(self) -> None:
        rows = self.db.list_keywords()
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            check.setCheckState(Qt.CheckState.Checked if row["enabled"] else Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, row["id"])
            self.table.setItem(i, 0, check)
            self.table.setItem(i, 1, QTableWidgetItem(row["keyword"]))
            self.table.setItem(i, 2, QTableWidgetItem((row["created_at"] or "")[:10]))
        self.table.blockSignals(False)
        enabled = sum(1 for r in rows if r["enabled"])
        self.count_label.setText(f"{len(rows)} từ khoá, {enabled} đang bật")

    def _add_from_input(self) -> None:
        lines = self.input.toPlainText().splitlines()
        added = self.db.add_keywords(lines)
        self.input.clear()
        self.reload()
        if lines and not added:
            QMessageBox.information(self, "Từ khoá", "Các từ khoá này đã có trong danh sách.")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Nhập từ khoá", "", "Text (*.txt)")
        if path:
            added = self.db.add_keywords(Path(path).read_text(encoding="utf-8-sig").splitlines())
            self.reload()
            QMessageBox.information(self, "Từ khoá", f"Đã thêm {added} từ khoá mới.")

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Xuất từ khoá", "keywords.txt", "Text (*.txt)")
        if path:
            Path(path).write_text("\n".join(r["keyword"] for r in self.db.list_keywords()), encoding="utf-8")

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self.db.set_keyword_enabled(item.data(Qt.ItemDataRole.UserRole),
                                        item.checkState() == Qt.CheckState.Checked)
            self.reload()

    def _set_all(self, enabled: bool) -> None:
        for row in self.db.list_keywords():
            self.db.set_keyword_enabled(row["id"], enabled)
        self.reload()

    def _delete_selected(self) -> None:
        ids = sorted({self.table.item(idx.row(), 0).data(Qt.ItemDataRole.UserRole)
                      for idx in self.table.selectionModel().selectedRows()})
        if not ids:
            return
        if QMessageBox.question(self, "Xoá từ khoá", f"Xoá {len(ids)} từ khoá đã chọn?") \
                == QMessageBox.StandardButton.Yes:
            self.db.delete_keywords(ids)
            self.reload()
