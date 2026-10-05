"""Dán link watchcount: đọc link thành cài đặt, dựng lại URL, ô Cài đặt quét."""
import os

import pytest

from app import config
from app.core.scan_job import ScanCallbacks, run_scan
from app.db.database import Database
from app.scraper import watchcount
from tests.test_core import FakeClient

USER_LINK = ("https://www.watchcount.com/sold/Personalized+suncatcher/-/all"
             "?condition=new&lastSoldDate=30days&offset=60&site=EBAY_US&sortBy=bestmatch")


def _build(parsed: dict, offset: int = 0) -> str:
    return watchcount.build_search_url(
        parsed["keyword"], parsed["site"], parsed["sort_by"], parsed["listing_type"], None, offset,
        status=parsed["status"], last_sold_within=parsed["last_sold_within"], condition=parsed["condition"],
        category=parsed["category"], min_price=parsed["min_price"], max_price=parsed["max_price"],
        exact_match=parsed["exact_match"], extra_params=parsed["extra_params"])


def test_parse_user_link_round_trips():
    parsed = watchcount.parse_search_url(USER_LINK)
    assert parsed["status"] == "sold" and parsed["keyword"] == "Personalized suncatcher"
    assert (parsed["listing_type"], parsed["condition"], parsed["last_sold_within"]) == ("all", "new", "30days")
    assert parsed["category"] == "" and parsed["extra_params"] == {} and parsed["notes"] == []
    assert _build(parsed, 60) == USER_LINK


def test_parse_sold_link_with_category_price_exact():
    link = ("https://www.watchcount.com/sold/Personalized+suncatcher/home-decor_10033/fixedprice"
            "?condition=new&exactKeywordMatch=true&lastSoldDate=30days&maxPrice=30&minPrice=10"
            "&site=EBAY_US&sortBy=bestmatch")
    parsed = watchcount.parse_search_url(link)
    assert parsed["category"] == "home-decor_10033"
    assert (parsed["min_price"], parsed["max_price"], parsed["exact_match"]) == (10, 30, True)
    assert watchcount.category_label("home-decor_10033") == "Home Decor (#10033)"
    assert watchcount.category_label("home-garden_11700") == "Home & Garden"
    assert _build(parsed) == link


def test_parse_live_link_keeps_unknown_filters():
    link = ("https://watchcount.com/live/a%252Fb+c/-/fixedprice?freeShippingOnly=true&itemLocation=US"
            "&seller=abc&site=EBAY_GB&sortBy=price&sortOrder=desc&startTimeFrom=12hours")
    parsed = watchcount.parse_search_url(link)
    assert parsed["keyword"] == "a/b c" and parsed["site"] == "EBAY_GB"
    assert parsed["sort_by"] == "price_desc" and parsed["start_age_days"] == 0.5
    assert parsed["extra_params"] == {"freeShippingOnly": "true", "itemLocation": "US", "seller": "abc"}
    url = _build(parsed)
    assert "seller=abc" in url and "freeShippingOnly=true" in url and "/live/a%252Fb+c/-/fixedprice" in url


def test_parse_link_defaults_and_notes():
    live = watchcount.parse_search_url("https://www.watchcount.com/live/mug/-/all?site=EBAY_US")
    assert live["sort_by"] == "watchcount"  # không có sortBy = mặc định Watch Count của tab Live
    sold = watchcount.parse_search_url("https://www.watchcount.com/sold/mug/-/all?sortBy=bestselling&site=EBAY_XX")
    assert sold["sort_by"] == "bestmatch" and sold["site"] == "EBAY_US" and len(sold["notes"]) == 2
    assert watchcount.parse_search_url("https://www.watchcount.com/sold/-/-/all")["keyword"] == ""


@pytest.mark.parametrize("link", ["https://www.ebay.com/sch/i.html?_nkw=mug", "https://www.watchcount.com/",
                                  "https://www.watchcount.com/login", "không phải link"])
def test_parse_rejects_non_search_links(link):
    with pytest.raises(ValueError):
        watchcount.parse_search_url(link)


def test_extra_params_cannot_override_tool_params():
    url = watchcount.build_search_url("x", status="sold", offset=20, category="bad/../path",
                                      extra_params={"offset": "999", "sortBy": "listdate", "seller": "a b"})
    assert url == "https://www.watchcount.com/sold/x/-/fixedprice?offset=20&seller=a%20b&site=EBAY_US&sortBy=bestmatch"


def test_scan_sends_new_search_settings(tmp_path):
    cfg = config._deep_merge(config.DEFAULTS, {})
    cfg["search"].update(delay_min=0, delay_max=0, category="home-garden_11700", min_price=5, max_price=None,
                         exact_match=True, extra_params={"seller": "abc"})
    fake = FakeClient(pages=1)
    run_scan(Database(tmp_path / "t.db"), cfg, ["mug"], "manual", ScanCallbacks(), lambda: fake)
    assert fake.urls == ["https://www.watchcount.com/sold/mug/home-garden_11700/fixedprice"
                         "?exactKeywordMatch=true&lastSoldDate=7days&minPrice=5&seller=abc&site=EBAY_US&sortBy=bestmatch"]


class ExactMatchFake(FakeClient):
    """Exact Match: watchcount lọc trên từng trang nên trang giữa có thể trống mà vẫn còn nextOffset."""

    def search(self, url, **kwargs):
        result = super().search(url, **kwargs)
        if "offset=20" in url or "offset=40" in url:
            result["items"] = []
        return result


@pytest.mark.parametrize("exact, pages_used", [(True, 4), (False, 2)])
def test_exact_match_keeps_paging_past_empty_pages(tmp_path, exact, pages_used):
    cfg = config._deep_merge(config.DEFAULTS, {})
    cfg["search"].update(delay_min=0, delay_max=0, exact_match=exact, stop_after_empty_pages=1)
    fake = ExactMatchFake(pages=4)
    summary = run_scan(Database(tmp_path / "t.db"), cfg, ["mug"], "manual", ScanCallbacks(), lambda: fake)
    assert summary.pages_used == pages_used


def test_settings_page_applies_link(qapp):
    from app.ui.pages.settings_page import SettingsPage

    cfg = config._deep_merge(config.DEFAULTS, {})
    page = SettingsPage(cfg)
    parsed = watchcount.parse_search_url(
        "https://www.watchcount.com/live/mug/home-decor_10033/auction?minPrice=3&seller=abc&startTimeFrom=3days"
        "&sortBy=listdate&site=EBAY_US")
    box = page.link_confirm_box(parsed)
    assert box.checkBox().isChecked() and "seller=abc" in box.informativeText()
    page.apply_parsed_link(parsed, clear_filters=box.checkBox().isChecked())
    page.write_to_config()
    s = cfg["search"]
    assert (s["status"], s["sort_by"], s["listing_type"], s["category"]) == ("live", "listdate", "auction",
                                                                             "home-decor_10033")
    assert (s["min_price"], s["max_price"], s["extra_params"]) == (3, None, {"seller": "abc"})
    values = {r["field"]: r["value"] for r in cfg["scan_filters"]}
    assert values.pop("start_age_days") == 3 and set(values.values()) == {None}

    page.load_from_config()  # danh mục con vẫn còn sau khi nạp lại
    assert page.category.currentData() == "home-decor_10033"
    page.extra_clear_btn.click()
    page.write_to_config()
    assert s["extra_params"] == {}


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
