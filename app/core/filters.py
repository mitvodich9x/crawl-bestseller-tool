"""Rule-based filtering of product records. A rule with an empty value is ignored."""
import operator
from dataclasses import dataclass
from datetime import datetime, timezone

from app.scraper.parsing import parse_iso_utc

FIELD_LABELS = {
    "start_age_days": "Start (số ngày từ lúc đăng)",
    "last_sold_age_days": "Bán gần nhất (số ngày trước)",
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

# Tab Sold chỉ trả listing đã bán hết: quantitySold luôn là 1 và tốc độ bán watchcount tính bằng 1 / số ngày listing
# đã chạy, nên các chỉ số này không nói lên listing bán chạy hay không (Sell one <= 7 thành ra chỉ là Start <= 7).
SOLD_TAB_IGNORED = ("total_sold", "days_per_sale", "sold_per_day")


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

    def describe(self) -> str:
        return f"{FIELD_LABELS.get(self.field, self.field)} {self.op} {self.value:g}"


_AGE_FIELDS = {"start_age_days": "start_time", "last_sold_age_days": "last_sold_at"}


def field_value(product: dict, field: str, now: datetime | None = None) -> float | None:
    if field in _AGE_FIELDS:
        moment = parse_iso_utc(product.get(_AGE_FIELDS[field]))
        if moment is None:
            return None
        now = now or datetime.now(timezone.utc)
        return (now - moment).total_seconds() / 86400
    value = product.get(field)
    return None if value is None else float(value)


def passes(product: dict, rule: FilterRule, now: datetime | None = None) -> bool:
    if not rule.active:
        return True
    actual = field_value(product, rule.field, now)
    # a missing metric (e.g. no sales yet -> no sell-one speed) cannot satisfy an active rule
    return actual is not None and OPERATORS[rule.op](actual, rule.value)


def matches(product: dict, rules: list[FilterRule], now: datetime | None = None) -> bool:
    return all(passes(product, rule, now) for rule in rules)


def apply(products: list[dict], rules: list[FilterRule], now: datetime | None = None) -> list[dict]:
    return [p for p in products if matches(p, rules, now)]


def rejection_counts(products: list[dict], rules: list[FilterRule], now: datetime | None = None) -> dict[str, int]:
    """Số sản phẩm trượt từng điều kiện (một sản phẩm có thể trượt nhiều điều kiện)."""
    counts = {}
    for rule in rules:
        failed = sum(1 for p in products if not passes(p, rule, now))
        if failed:
            counts[rule.describe()] = failed
    return counts


def rules_from_config(items: list[dict]) -> list[FilterRule]:
    return [FilterRule.from_dict(d) for d in items if d.get("field") in FIELD_LABELS]


def ignored_for_status(items: list[dict], status: str) -> list[dict]:
    """Các điều kiện đang bật nhưng bị bỏ qua ở tab này."""
    if status != "sold":
        return []
    return [d for d in items if d.get("field") in SOLD_TAB_IGNORED and d.get("value") not in ("", None)]


def rules_for_status(items: list[dict], status: str) -> list[dict]:
    """Bộ lọc thật sự áp dụng khi quét tab này: tab Sold tắt các chỉ số tổng đơn / tốc độ bán."""
    if status != "sold":
        return [dict(d) for d in items]
    return [{**d, "value": None} if d.get("field") in SOLD_TAB_IGNORED else dict(d) for d in items]
