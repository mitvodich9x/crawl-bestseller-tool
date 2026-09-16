"""Rule-based filtering of product records. A rule with an empty value is ignored."""
import operator
from dataclasses import dataclass
from datetime import datetime, timezone

from app.scraper.parsing import parse_iso_utc

FIELD_LABELS = {
    "start_age_days": "Start (số ngày từ lúc đăng)",
    "total_sold": "Tổng đơn",
    "days_per_sale": "Sell one (số ngày bán 1 đơn)",
    "sold_per_day": "Số đơn trung bình / ngày",
    "watchers": "Lượt theo dõi",
    "price": "Giá (USD)",
}

OPERATORS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "=": operator.eq,
}


@dataclass
class FilterRule:
    field: str
    op: str
    value: float | None

    @classmethod
    def from_dict(cls, data: dict) -> "FilterRule":
        value = data.get("value")
        if value in ("", None):
            value = None
        else:
            value = float(value)
        return cls(field=data["field"], op=data.get("op", ">="), value=value)

    def to_dict(self) -> dict:
        return {"field": self.field, "op": self.op, "value": self.value}

    @property
    def active(self) -> bool:
        return self.value is not None


def field_value(product: dict, field: str, now: datetime | None = None) -> float | None:
    if field == "start_age_days":
        start = parse_iso_utc(product.get("start_time"))
        if start is None:
            return None
        now = now or datetime.now(timezone.utc)
        return (now - start).total_seconds() / 86400
    value = product.get(field)
    return None if value is None else float(value)


def matches(product: dict, rules: list[FilterRule], now: datetime | None = None) -> bool:
    for rule in rules:
        if not rule.active:
            continue
        actual = field_value(product, rule.field, now)
        # a missing metric (e.g. no sales yet -> no sell-one speed) cannot satisfy an active rule
        if actual is None or not OPERATORS[rule.op](actual, rule.value):
            return False
    return True


def apply(products: list[dict], rules: list[FilterRule], now: datetime | None = None) -> list[dict]:
    return [p for p in products if matches(p, rules, now)]


def rules_from_config(items: list[dict]) -> list[FilterRule]:
    return [FilterRule.from_dict(d) for d in items if d.get("field") in FIELD_LABELS]
