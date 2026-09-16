from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QGridLayout, QLabel, QLineEdit, QWidget

from app.core.filters import FIELD_LABELS, OPERATORS, FilterRule


class FilterEditor(QWidget):
    """One row per metric: operator + value. An empty value means the rule is off."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(2, 1)
        self._rows: dict[str, tuple[QComboBox, QLineEdit]] = {}
        for row, (field, label) in enumerate(FIELD_LABELS.items()):
            op = QComboBox()
            op.addItems(list(OPERATORS))
            op.setFixedWidth(64)
            value = QLineEdit()
            value.setPlaceholderText("để trống = không lọc")
            op.currentIndexChanged.connect(self.changed)
            value.textChanged.connect(self.changed)
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(op, row, 1)
            grid.addWidget(value, row, 2)
            self._rows[field] = (op, value)

    def set_rules(self, rules: list[dict]) -> None:
        by_field = {r["field"]: r for r in rules}
        for field, (op, value) in self._rows.items():
            rule = by_field.get(field, {})
            op.blockSignals(True)
            value.blockSignals(True)
            op.setCurrentText(rule.get("op") or (">=" if field in ("total_sold", "watchers", "sold_per_day") else "<="))
            raw = rule.get("value")
            value.setText("" if raw in (None, "") else f"{float(raw):g}")
            op.blockSignals(False)
            value.blockSignals(False)

    def rule_dicts(self) -> list[dict]:
        result = []
        for field, (op, value) in self._rows.items():
            text = value.text().strip().replace(",", ".")
            try:
                parsed = float(text) if text else None
            except ValueError:
                parsed = None
            result.append({"field": field, "op": op.currentText(), "value": parsed})
        return result

    def rules(self) -> list[FilterRule]:
        return [FilterRule.from_dict(d) for d in self.rule_dicts()]
