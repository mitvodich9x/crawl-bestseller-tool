from datetime import date, datetime, timezone

import pytest

from app import config
from app.core import filters, scheduler
from app.core.scan_job import ScanCallbacks, run_scan
from app.db.database import Database
from app.scraper import watchcount
from app.scraper.parsing import parse_item, parse_sold_per_day

RAW = {
    "id": "237065838500",
    "title": "Funny Food Bikini T-Shirt",
    "image": "https://i.ebayimg.com/images/g/abc/s-l225.jpg",
    "quantitySold": 10,
    "oneUnitEvery": "5.0 sold/day",
    "quantitySoldRate": "150 sold per month",
    "startTime": "2026-09-13T10:00:00Z",
    "watchCount": 12,
    "price": [19.99, 24.99],
    "priceFormatted": "$19.99 to $24.99",
    "currency": "USD",
    "shipping": 0,
    "seller": "shop",
    "timeRunning": 2.0,
}
NOW = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("text,expected", [
    ("2.9 sold/day", 2.9),
    ("1.0 sold/week", 1 / 7),
    ("1.7 sold/month", 1.7 / 30.44),
    ("4.3 sold/year", 4.3 / 365),
    (None, None),
    ("garbage", None),
])
def test_parse_sold_per_day(text, expected):
    assert parse_sold_per_day(text) == (pytest.approx(expected) if expected else None)


def test_parse_item():
    p = parse_item(RAW)
    assert p["item_id"] == "237065838500"
    assert p["image_url"].endswith("/s-l500.jpg")
    assert p["item_url"] == "https://www.ebay.com/itm/237065838500"
    assert p["price"] == 19.99
    assert p["days_per_sale"] == pytest.approx(0.2)
    assert p["total_sold"] == 10


def test_parse_item_rate_fallback_from_time_running():
    p = parse_item({**RAW, "oneUnitEvery": None, "quantitySold": 6, "timeRunning": 3.0})
    assert p["sold_per_day"] == pytest.approx(2.0)


def test_filters_start_age_sell_one_and_blank_rule():
    p = parse_item(RAW)
    rules = filters.rules_from_config([
        {"field": "start_age_days", "op": "<=", "value": 7},
        {"field": "total_sold", "op": ">=", "value": ""},  # blank -> ignored
        {"field": "days_per_sale", "op": "<=", "value": 1},
    ])
    assert filters.matches(p, rules, NOW)
    old = {**p, "start_time": "2026-09-01T00:00:00+00:00"}
    assert not filters.matches(old, rules, NOW)
    slow = parse_item({**RAW, "oneUnitEvery": "1.0 sold/week"})
    assert not filters.matches(slow, rules, NOW)


def test_filter_missing_metric_fails_active_rule():
    no_sales = parse_item({**RAW, "quantitySold": 0, "oneUnitEvery": None})
    rules = [filters.FilterRule("days_per_sale", "<=", 7)]
    assert not filters.matches(no_sales, rules, NOW)


def test_schedule_every_two_days_across_month_and_year():
    s = {"mode": "every_n_days", "n_days": 2, "anchor_date": "2026-12-30", "time": "08:00"}
    assert scheduler.is_scan_day(date(2026, 12, 30), s)
    assert not scheduler.is_scan_day(date(2026, 12, 31), s)
    assert scheduler.is_scan_day(date(2027, 1, 1), s)
    assert scheduler.is_scan_day(date(2026, 12, 28), s)


def test_schedule_odd_even():
    assert scheduler.is_scan_day(date(2026, 9, 15), {"mode": "odd_days"})
    assert not scheduler.is_scan_day(date(2026, 9, 15), {"mode": "even_days"})


def test_should_run_and_catch_up_once():
    s = {"mode": "odd_days", "time": "08:00"}
    assert not scheduler.should_run(datetime(2026, 9, 15, 7, 59), s, None)
    assert scheduler.should_run(datetime(2026, 9, 15, 8, 0), s, None)
    assert scheduler.should_run(datetime(2026, 9, 15, 21, 0), s, "2026-09-13")  # app opened late
    assert not scheduler.should_run(datetime(2026, 9, 15, 21, 0), s, "2026-09-15")
    assert not scheduler.should_run(datetime(2026, 9, 16, 9, 0), s, None)
    assert not scheduler.should_run(datetime(2026, 9, 15, 9, 0), {"mode": "manual"}, None)


def test_next_run():
    s = {"mode": "even_days", "time": "08:00"}
    assert scheduler.next_run(datetime(2026, 9, 15, 9, 0), s, None) == datetime(2026, 9, 16, 8, 0)
    s = {"mode": "odd_days", "time": "08:00"}
    assert scheduler.next_run(datetime(2026, 9, 15, 7, 0), s, None) == datetime(2026, 9, 15, 8, 0)
    assert scheduler.next_run(datetime(2026, 9, 15, 9, 0), s, "2026-09-15") == datetime(2026, 9, 17, 8, 0)


def test_build_search_url_matches_site_format():
    url = watchcount.build_search_url("funny shirt", "EBAY_US", "bestselling", "fixedprice", "7days", 20)
    assert url == ("https://beta.watchcount.com/live/funny+shirt/-/fixedprice"
                   "?offset=20&site=EBAY_US&sortBy=bestselling&startTimeFrom=7days")
    url = watchcount.build_search_url("a/b", sort_by="watchcount")
    assert url == "https://beta.watchcount.com/live/a%252Fb/-/fixedprice?site=EBAY_US"


def test_start_within_param():
    assert watchcount.start_within_param(7) == "7days"
    assert watchcount.start_within_param(10) == "14days"
    assert watchcount.start_within_param(None) is None


def test_remaining_quota_user_and_guest():
    user = {"max_daily_standard_searches": 200, "standard_count": 2, "max_monthly_best_selling": 3,
            "best_selling_count": 1}
    assert watchcount.remaining_quota(user, "bestmatch") == 198
    assert watchcount.remaining_quota(user, "bestselling") == 2
    guest = {"max_standard": 20, "standard_count": 0}
    assert watchcount.remaining_quota(guest, "listdate") == 20


class FakeClient:
    """Two pages for every keyword; page 2 has no sales."""

    def __init__(self, quota=100, pages=2):
        self.quota = quota
        self.pages = pages
        self.urls = []

    def start(self):
        pass

    def close(self):
        pass

    def account_status(self):
        return {"logged_in": True, "usage": {"max_daily_standard_searches": self.quota, "standard_count": 0}}

    def search(self, url):
        self.urls.append(url)
        offset = int(url.split("offset=")[1].split("&")[0]) if "offset=" in url else 0
        page = offset // 20
        last = page >= self.pages - 1
        next_offset = None if last else offset + 20
        if page == 0:
            items = [RAW, {**RAW, "id": "1", "startTime": "2026-01-01T00:00:00Z"}]
        else:  # later pages have no sales at all
            items = [{**RAW, "id": f"p{page}", "quantitySold": 0, "oneUnitEvery": None}]
        return {"items": items, "total": 21, "nextOffset": next_offset}


def _cfg():
    cfg = config._deep_merge(config.DEFAULTS, {})
    cfg["search"].update(delay_min=0, delay_max=0)
    return cfg


def test_run_scan_saves_and_marks_kept(tmp_path):
    db = Database(tmp_path / "t.db")
    fake = FakeClient()
    summary = run_scan(db, _cfg(), ["funny shirt", "cat mug"], "manual", ScanCallbacks(), lambda: fake)
    assert summary.status == "completed"
    assert summary.pages_used == 4
    assert all("startTimeFrom=7days" in u and "sortBy=bestmatch" in u for u in fake.urls)
    rows = db.query_products(keyword="funny shirt")
    assert {r["item_id"] for r in rows} == {"237065838500", "1", "p1"}
    assert {r["item_id"] for r in db.query_products(keyword="funny shirt", kept_only=True)} == {"237065838500"}
    assert db.list_runs()[0]["status"] == "completed"


def test_run_scan_counts_each_item_once_when_pages_repeat_items(tmp_path):
    """watchcount repeats items across pages; the summary must not count them twice."""

    class RepeatingClient(FakeClient):
        def search(self, url):
            self.urls.append(url)
            offset = int(url.split("offset=")[1].split("&")[0]) if "offset=" in url else 0
            page = offset // 20
            return {"items": [RAW, {**RAW, "id": f"only{page}"}], "total": 6,
                    "nextOffset": None if page >= 2 else offset + 20}

    fake = RepeatingClient()
    cfg = _cfg()
    cfg["search"].update(max_pages=3, stop_after_empty_pages=0)
    summary = run_scan(Database(tmp_path / "t.db"), cfg, ["a"], "manual", ScanCallbacks(), lambda: fake)
    assert summary.pages_used == 3
    assert summary.total_found == 4  # RAW once + only0/only1/only2
    assert summary.total_kept == 4


def test_run_scan_stops_early_after_pages_without_sales(tmp_path):
    cfg = _cfg()
    cfg["search"].update(max_pages=50, stop_after_empty_pages=3)
    fake = FakeClient(pages=50)
    summary = run_scan(Database(tmp_path / "t.db"), cfg, ["a"], "manual", ScanCallbacks(), lambda: fake)
    assert summary.pages_used == 4  # page 1 has sales, then 3 empty ones


def test_run_scan_take_all_pages_when_early_stop_disabled(tmp_path):
    cfg = _cfg()
    cfg["search"].update(max_pages=50, stop_after_empty_pages=0)
    fake = FakeClient(pages=50)
    summary = run_scan(Database(tmp_path / "t.db"), cfg, ["a"], "manual", ScanCallbacks(), lambda: fake)
    assert summary.pages_used == 50
    assert fake.urls[-1].endswith("offset=980&site=EBAY_US&sortBy=bestmatch&startTimeFrom=7days")


def test_run_scan_max_pages_caps_a_long_keyword(tmp_path):
    cfg = _cfg()
    cfg["search"].update(max_pages=5, stop_after_empty_pages=0)
    fake = FakeClient(pages=50)
    summary = run_scan(Database(tmp_path / "t.db"), cfg, ["a"], "manual", ScanCallbacks(), lambda: fake)
    assert summary.pages_used == 5


def test_run_scan_spreads_quota_across_keywords(tmp_path):
    db = Database(tmp_path / "t.db")
    fake = FakeClient(quota=2)
    summary = run_scan(db, _cfg(), ["a", "b"], "manual", ScanCallbacks(), lambda: fake)
    assert summary.pages_used == 2
    assert [u.split("/live/")[1].split("/")[0] for u in fake.urls] == ["a", "b"]
