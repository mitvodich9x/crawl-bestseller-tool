"""Đẩy SP trend lên Lumi: dữ liệu gửi đi, chia lô, báo lỗi, đánh dấu đã đẩy."""
import json

import pytest

from app import lumi_api
from app.db.database import Database


def test_normalize_base_url():
    assert lumi_api.normalize_base_url("") == lumi_api.DEFAULT_BASE_URL
    assert lumi_api.normalize_base_url("app.lumihubs.com/") == "https://app.lumihubs.com"
    assert lumi_api.normalize_base_url("http://localhost:5173/api") == "http://localhost:5173"


def test_item_payload_keeps_numbers_and_trims_text():
    product = {"item_id": "123456789012", "title": "  Cat mug ", "price": 19.99, "total_sold": 42,
               "days_per_sale": 1.5, "watchers": None, "keyword": "k" * 300, "start_time": "",
               "last_sold_at": "2026-10-20T08:00:00+00:00", "seller": None}
    item = lumi_api.item_payload(product)
    assert item["title"] == "Cat mug" and item["price"] == 19.99 and item["total_sold"] == 42
    assert item["watchers"] is None and item["start_time"] is None
    assert len(item["keyword"]) == 200 and item["last_sold_at"].startswith("2026-10-20")


def test_push_trends_batches_and_sums(monkeypatch):
    calls = []

    def fake_post(base_url, token, body, timeout):
        calls.append(len(body["items"]))
        return {"created": len(body["items"]), "updated": 0}

    monkeypatch.setattr(lumi_api, "_post", fake_post)
    products = [{"item_id": str(100000 + i), "title": f"T{i}"} for i in range(lumi_api.BATCH_SIZE + 3)]
    assert lumi_api.push_trends("", "tok", products) == {"created": len(products), "updated": 0}
    assert calls == [lumi_api.BATCH_SIZE, 3]
    json.dumps(lumi_api.item_payload(products[0]))  # gửi được dạng JSON


def test_push_trends_requires_token():
    with pytest.raises(lumi_api.LumiError):
        lumi_api.push_trends("", "  ", [{"item_id": "123456", "title": "x"}])


def test_mark_pushed(tmp_path):
    db = Database(tmp_path / "t.db")
    db.mark_pushed(["1", "2"])
    db.mark_pushed(["2"])
    assert db.pushed_ids() == {"1", "2"}
