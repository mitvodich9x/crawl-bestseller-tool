from datetime import date, datetime, timedelta, timezone

import pytest

from app import config
from app.core import filters, scheduler
from app.core.scan_job import ScanCallbacks, run_scan
from app.db.database import Database
from app.scraper import watchcount
from app.scraper.parsing import parse_item, parse_sold_per_day

def iso_days_ago(days: float) -> str:
    """Mốc thời gian tương đối để test không phụ thuộc ngày chạy."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


RAW = {
    "id": "237065838500",
    "title": "Funny Food Bikini T-Shirt",
    "image": "https://i.ebayimg.com/images/g/abc/s-l225.jpg",
    "quantitySold": 10,
    "oneUnitEvery": "5.0 sold/day",
    "quantitySoldRate": "150 sold per month",
    "startTime": iso_days_ago(2),
    "watchCount": 12,
    "price": [19.99, 24.99],
    "priceFormatted": "$19.99 to $24.99",
    "currency": "USD",
    "shipping": 0,
    "seller": "shop",
    "timeRunning": 2.0,
}
NOW = datetime.now(timezone.utc)


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
    assert url == ("https://www.watchcount.com/live/funny+shirt/-/fixedprice"
                   "?offset=20&site=EBAY_US&sortBy=bestselling&startTimeFrom=7days")
    url = watchcount.build_search_url("a/b", sort_by="watchcount")
    assert url == "https://www.watchcount.com/live/a%252Fb/-/fixedprice?site=EBAY_US"


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


@pytest.mark.parametrize("url,expected", [
    ("https://www.watchcount.com/challenge?returnURL=/live/cat+mug", True),
    ("https://www.watchcount.com/live/cat+mug/-/fixedprice?site=EBAY_US", False),
    (None, False),
])
def test_is_challenge_url(url, expected):
    assert watchcount.is_challenge_url(url) is expected


def test_run_scan_best_selling_needs_login(tmp_path):
    """Best Selling chỉ dành cho tài khoản -> dừng ngay, không tốn lượt."""

    class GuestClient(FakeClient):
        def account_status(self):
            return {"logged_in": False, "usage": {}}

    fake = GuestClient()
    db = Database(tmp_path / "t.db")
    cfg = _cfg()
    cfg["search"].update(status="live", sort_by="bestselling")
    summary = run_scan(db, cfg, ["a"], "manual", ScanCallbacks(), lambda: fake)
    assert summary.status == "need_login"
    assert "Đăng nhập watchcount" in summary.error
    assert summary.pages_used == 0
    assert fake.urls == []
    assert db.list_runs()[0]["status"] == "need_login"


def test_run_scan_guest_can_scan_best_match(tmp_path):
    class GuestClient(FakeClient):
        def account_status(self):
            return {"logged_in": False, "usage": {"max_standard": 20, "standard_count": 0}}

    summary = run_scan(Database(tmp_path / "t.db"), _cfg(), ["a"], "manual", ScanCallbacks(), lambda: GuestClient())
    assert summary.status == "completed"


def test_run_scan_reopens_visible_browser_on_challenge(tmp_path):
    """Chạy ẩn bị reCAPTCHA chặn -> mở cửa sổ hiện cho người dùng tích rồi quét tiếp, không báo 'cần đăng nhập'."""

    class HeadlessClient(FakeClient):
        headless = True

        def search(self, url, **kwargs):
            raise watchcount.ChallengeError(watchcount.CHALLENGE_MESSAGE)

    visible = FakeClient()
    visible.headless = False
    calls = []

    def factory(headless=True):
        calls.append(headless)
        return HeadlessClient() if headless else visible

    alerts = []
    summary = run_scan(Database(tmp_path / "t.db"), _cfg(), ["a"], "manual",
                       ScanCallbacks(attention=alerts.append), factory)
    assert calls == [True, False]
    assert summary.status == "completed"
    assert len(visible.urls) == 2
    assert alerts == [watchcount.CHALLENGE_MESSAGE]


def test_run_scan_scans_every_keyword_after_challenge(tmp_path):
    """Qua reCAPTCHA ở từ khoá đầu rồi thì các từ khoá sau vẫn được quét trong cửa sổ đang hiện."""

    class HeadlessClient(FakeClient):
        headless = True

        def search(self, url, **kwargs):
            raise watchcount.ChallengeError(watchcount.CHALLENGE_MESSAGE)

    visible = FakeClient()
    visible.headless = False
    summary = run_scan(Database(tmp_path / "t.db"), _cfg(), ["funny shirt", "cat mug"], "manual", ScanCallbacks(),
                       lambda headless=True: HeadlessClient() if headless else visible)
    assert summary.status == "completed"
    assert list(summary.per_keyword) == ["funny shirt", "cat mug"] and summary.skipped == []
    assert [u.split("/sold/")[1].split("/")[0] for u in visible.urls] == ["funny+shirt"] * 2 + ["cat+mug"] * 2


def test_run_scan_reports_keywords_skipped_when_quota_runs_out(tmp_path):
    messages = []
    summary = run_scan(Database(tmp_path / "t.db"), _cfg(), ["a", "b", "c"], "manual",
                       ScanCallbacks(log=messages.append), lambda: FakeClient(quota=1))
    assert summary.status == "quota_exhausted"
    assert list(summary.per_keyword) == ["a"] and summary.skipped == ["b", "c"]
    assert any("a: 2 sản phẩm, 1 đạt bộ lọc" in m for m in messages)
    assert any("chưa quét xong 2 từ khoá (hết lượt tìm kiếm của watchcount): b, c" in m for m in messages)


def test_run_scan_challenge_not_passed_is_blocked(tmp_path):
    class StuckClient(FakeClient):
        headless = False

        def search(self, url, **kwargs):
            raise watchcount.ChallengeError(watchcount.CHALLENGE_MESSAGE)

    summary = run_scan(Database(tmp_path / "t.db"), _cfg(), ["a"], "manual", ScanCallbacks(), lambda: StuckClient())
    assert summary.status == "blocked"
    assert "reCAPTCHA" in summary.error


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

    def search(self, url, **kwargs):
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
    assert all("sortBy=bestmatch" in u and "startTimeFrom" not in u for u in fake.urls)
    rows = db.query_products(keyword="funny shirt")
    assert {r["item_id"] for r in rows} == {"237065838500", "1", "p1"}
    # tab Sold bỏ qua Sell one, chỉ còn Start <= 7 loại item "1"
    assert {r["item_id"] for r in db.query_products(keyword="funny shirt", kept_only=True)} == {"237065838500", "p1"}
    assert db.list_runs()[0]["status"] == "completed"


def test_run_scan_counts_each_item_once_when_pages_repeat_items(tmp_path):
    """watchcount repeats items across pages; the summary must not count them twice."""

    class RepeatingClient(FakeClient):
        def search(self, url, **kwargs):
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
    assert fake.urls[-1].endswith("offset=980&site=EBAY_US&sortBy=bestmatch")


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
    assert [u.split("/sold/")[1].split("/")[0] for u in fake.urls] == ["a", "b"]


def test_default_scan_uses_sold_tab(tmp_path):
    fake = FakeClient()
    run_scan(Database(tmp_path / "t.db"), _cfg(), ["cat mug"], "manual", ScanCallbacks(), lambda: fake)
    assert fake.urls[0] == ("https://www.watchcount.com/sold/cat+mug/-/fixedprice"
                            "?lastSoldDate=7days&site=EBAY_US&sortBy=bestmatch")


def test_live_scan_applies_sell_one_and_sends_start_filter(tmp_path):
    db = Database(tmp_path / "t.db")
    fake = FakeClient()
    cfg = _cfg()
    cfg["search"]["status"] = "live"
    run_scan(db, cfg, ["funny shirt"], "manual", ScanCallbacks(), lambda: fake)
    assert all("/live/" in u and "startTimeFrom=7days" in u for u in fake.urls)
    assert {r["item_id"] for r in db.query_products(kept_only=True)} == {"237065838500"}


def test_sold_tab_ignores_sales_metrics():
    items = config.DEFAULTS["scan_filters"] + [{"field": "total_sold", "op": ">=", "value": 5}]
    sold = {d["field"]: d["value"] for d in filters.rules_for_status(items, "sold")}
    assert sold["days_per_sale"] is None and sold["total_sold"] is None and sold["start_age_days"] == 7
    assert filters.rules_for_status(items, "live") == items
    assert {d["field"] for d in filters.ignored_for_status(items, "sold")} == {"days_per_sale", "total_sold"}
    assert filters.ignored_for_status(items, "live") == []


def test_rejection_counts_per_rule():
    fresh = parse_item(RAW)
    old = parse_item({**RAW, "id": "2", "startTime": iso_days_ago(30), "oneUnitEvery": "1.0 sold/month"})
    rules = filters.rules_from_config(config.DEFAULTS["scan_filters"])
    assert filters.rejection_counts([fresh, old], rules) == {
        "Start (số ngày từ lúc đăng) <= 7": 1, "Sell one (số ngày bán 1 đơn) <= 7": 1}


def test_scan_log_explains_rejections(tmp_path):
    messages = []
    run_scan(Database(tmp_path / "t.db"), _cfg(), ["a"], "manual", ScanCallbacks(log=messages.append),
             lambda: FakeClient(pages=1))
    assert any(m.startswith("Tab Sold: bỏ qua điều kiện Sell one") for m in messages)
    assert any("bị loại vì: Start (số ngày từ lúc đăng) <= 7 (1 SP)" in m for m in messages)


def test_sold_tab_falls_back_to_best_match_for_live_only_sorts():
    url = watchcount.build_search_url("x", sort_by="bestselling", status="sold")
    assert "sortBy=bestmatch" in url and "/sold/" in url
    assert watchcount.valid_sort("live", "bestselling") == "bestselling"
    url = watchcount.build_search_url("x", sort_by="price_desc", status="sold", last_sold_within="30days")
    assert url.endswith("?lastSoldDate=30days&site=EBAY_US&sortBy=price&sortOrder=desc")


def test_sold_url_with_condition_matches_web_link():
    # link mẫu trong trang Hướng dẫn, mục "Cào ra kết quả giống một link watchcount"
    url = watchcount.build_search_url("Personalized suncatcher", "EBAY_US", "bestmatch", "all", None, 60,
                                      status="sold", last_sold_within="30days", condition="new")
    assert url == ("https://www.watchcount.com/sold/Personalized+suncatcher/-/all"
                   "?condition=new&lastSoldDate=30days&offset=60&site=EBAY_US&sortBy=bestmatch")
    assert "condition" not in watchcount.build_search_url("x", status="sold", condition="")


def test_live_tab_ignores_last_sold_filter():
    url = watchcount.build_search_url("x", status="live", last_sold_within="7days")
    assert "lastSoldDate" not in url and "/live/" in url


def test_parse_sold_item_and_last_sold_filter():
    raw = {**RAW, "lastSoldDate": iso_days_ago(2), "lastSoldFor": 25, "lastSoldForFormatted": "$25"}
    p = parse_item(raw)
    assert p["last_sold_price"] == 25.0 and p["last_sold_price_text"] == "$25"
    assert filters.matches(p, [filters.FilterRule("last_sold_age_days", "<=", 3)])
    assert not filters.matches(p, [filters.FilterRule("last_sold_age_days", "<=", 1)])
    assert parse_item(RAW)["last_sold_at"] is None


def test_database_adds_new_columns_to_old_db(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE products (item_id TEXT PRIMARY KEY, title TEXT, image_url TEXT, item_url TEXT, "
                     "price REAL, price_text TEXT, currency TEXT, shipping REAL, total_sold INTEGER, "
                     "one_unit_every TEXT, sold_per_day REAL, days_per_sale REAL, sold_rate_text TEXT, "
                     "watchers INTEGER, start_time TEXT, seller TEXT, category TEXT, condition TEXT, "
                     "quantity_available INTEGER, est_sales TEXT, raw_json TEXT, first_seen TEXT NOT NULL, "
                     "last_seen TEXT NOT NULL, last_run_id INTEGER)")
    db = Database(path)
    run_id = db.start_run("manual")
    db.save_products(run_id, "k", [parse_item({**RAW, "lastSoldFor": 9})], set())
    assert db.query_products(keyword="k")[0]["last_sold_price"] == 9.0


def test_delete_results_by_keyword_by_run_and_all(tmp_path):
    import sqlite3
    db = Database(tmp_path / "t.db")
    run_scan(db, _cfg(), ["a", "b"], "manual", ScanCallbacks(), lambda: FakeClient())
    run_id = db.list_runs()[0]["id"]

    # theo từ khoá: sản phẩm vẫn còn vì từ khoá b cũng tìm thấy chúng, lịch sử giữ nguyên
    assert db.delete_results(keyword="a") == 3
    assert db.query_products(keyword="a") == [] and len(db.query_products(keyword="b")) == 3
    assert db.keywords_with_products() == ["b"] and len(db.list_runs()) == 1

    # theo lần quét: bỏ luôn lần quét khỏi lịch sử và sản phẩm không còn từ khoá nào
    assert db.delete_results(run_id=run_id) == 3
    assert db.query_products() == [] and db.list_runs() == []
    with sqlite3.connect(tmp_path / "t.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM product_snapshots").fetchone()[0] == 0

    # tất cả
    run_scan(db, _cfg(), ["a"], "manual", ScanCallbacks(), lambda: FakeClient())
    assert db.delete_results() == 3
    assert db.query_products() == [] and db.list_runs() == [] and db.keywords_with_products() == []
