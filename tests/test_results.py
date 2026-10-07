"""Gom dữ liệu trang Kết quả và xuất Excel hai sheet."""
import zipfile

from app.core.results import keyword_summary, merge_keywords
from app.export.excel import export_products, export_tables


def test_merge_keywords_one_card_per_product_kept_if_any_keyword_kept():
    rows = [
        {"item_id": "1", "keyword": "cat mug", "kept": 0, "title": "A"},
        {"item_id": "1", "keyword": "funny mug", "kept": 1, "title": "A"},
        {"item_id": "2", "keyword": "cat mug", "kept": 0, "title": "B"},
    ]
    merged = {p["item_id"]: p for p in merge_keywords(rows)}
    assert len(merged) == 2
    assert merged["1"]["keyword"] == "cat mug, funny mug" and merged["1"]["kept"] == 1
    assert merged["2"]["kept"] == 0


def test_keyword_summary_counts_and_lists_enabled_keywords_without_products():
    rows = [
        {"item_id": "1", "keyword": "cat mug", "kept": 0},
        {"item_id": "2", "keyword": "cat mug", "kept": 1},
        {"item_id": "1", "keyword": "funny mug", "kept": 1},
    ]
    assert keyword_summary(rows, ["Cat Mug", "dog bowl"]) == [("Cat Mug", 2, 1), ("dog bowl", 0, 0), ("funny mug", 1, 1)]
    assert keyword_summary([]) == []


def _sheet_names(path) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read("xl/workbook.xml").decode("utf-8")


def test_export_tables_writes_one_sheet_per_table(tmp_path):
    product = {"item_id": "1", "title": "A", "keyword": "k", "image_url": "https://i.ebayimg.com/x/s-l500.jpg"}
    path = export_tables([("1. Cào về", [product]), ("2. Đạt bộ lọc", [])], tmp_path / "out.xlsx")
    names = _sheet_names(path)
    assert "1. Cào về" in names and "2. Đạt bộ lọc" in names


def test_export_products_keeps_single_sheet(tmp_path):
    path = export_products([{"item_id": "1", "title": "A"}], tmp_path / "one.xlsx")
    assert 'name="Bestseller"' in _sheet_names(path)
