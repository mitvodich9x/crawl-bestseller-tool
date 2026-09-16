"""Convert watchcount `window.searchResult.items[]` entries into flat product records."""
import json
import re
from datetime import datetime, timezone

_RATE_RE = re.compile(r"([\d.,]+)\s*sold\s*/\s*(hour|day|week|month|year)", re.I)
_PERIOD_DAYS = {"hour": 1 / 24, "day": 1.0, "week": 7.0, "month": 30.44, "year": 365.0}


def parse_sold_per_day(one_unit_every: str | None) -> float | None:
    """'2.9 sold/day' -> 2.9, '1.0 sold/week' -> 0.1428..., None when missing."""
    if not one_unit_every:
        return None
    match = _RATE_RE.search(one_unit_every)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    return amount / _PERIOD_DAYS[match.group(2).lower()]


def parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def large_image(url: str | None) -> str | None:
    """eBay thumbnails come as s-l225; s-l500 is sharp enough for cards and export."""
    if not url:
        return url
    return re.sub(r"/s-l\d+\.", "/s-l500.", url)


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_item(raw: dict) -> dict:
    total_sold = int(raw.get("quantitySold") or 0)
    sold_per_day = parse_sold_per_day(raw.get("oneUnitEvery"))
    if sold_per_day is None and total_sold > 0:
        running_days = _to_float(raw.get("timeRunning"))
        if running_days:
            sold_per_day = total_sold / max(running_days, 1.0)
    prices = raw.get("price") or []
    if not isinstance(prices, list):
        prices = [prices]
    numeric_prices = [p for p in (_to_float(x) for x in prices) if p is not None]
    start = parse_iso_utc(raw.get("startTime"))
    item_id = str(raw["id"])

    return {
        "item_id": item_id,
        "title": raw.get("title") or "",
        "image_url": large_image(raw.get("image")),
        "item_url": f"https://www.ebay.com/itm/{item_id}",
        "price": min(numeric_prices) if numeric_prices else None,
        "price_text": raw.get("priceFormatted"),
        "currency": raw.get("currency"),
        "shipping": _to_float(raw.get("shipping")),
        "total_sold": total_sold,
        "one_unit_every": raw.get("oneUnitEvery"),
        "sold_per_day": sold_per_day,
        "days_per_sale": (1.0 / sold_per_day) if sold_per_day else None,
        "sold_rate_text": raw.get("quantitySoldRate"),
        "watchers": int(raw.get("watchCount") or 0),
        "start_time": start.isoformat() if start else None,
        "seller": raw.get("seller"),
        "category": raw.get("primaryCategoryTree"),
        "condition": raw.get("condition"),
        "quantity_available": raw.get("quantityAvailable"),
        "est_sales": raw.get("estimatedTotalSalesFormatted"),
        "raw_json": json.dumps(raw, ensure_ascii=False),
    }
