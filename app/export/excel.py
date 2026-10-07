"""Export product rows to .xlsx: keyword, title, image first, then the other metrics.

Trang Kết quả xuất hai sheet: "1. Cào về" (mọi sản phẩm đang hiện ở Bảng 1) và "2. Đạt bộ lọc" (Bảng 2).
"""
from datetime import datetime
from pathlib import Path

import xlsxwriter

from app.core.filters import field_value

COLUMNS = [
    # (header, width, getter)
    ("Từ khoá", 20, lambda p: p.get("keyword")),
    ("Tiêu đề", 60, lambda p: p.get("title")),
    ("Hình ảnh", 50, lambda p: p.get("image_url")),
    ("Tổng đơn", 10, lambda p: p.get("total_sold")),
    ("Tốc độ bán", 16, lambda p: p.get("one_unit_every")),
    ("Số ngày / 1 đơn", 14, lambda p: round(p["days_per_sale"], 2) if p.get("days_per_sale") else None),
    ("Đơn / ngày", 11, lambda p: round(p["sold_per_day"], 2) if p.get("sold_per_day") else None),
    ("Ngày start", 12, lambda p: (p.get("start_time") or "")[:10]),
    ("Số ngày từ start", 14, lambda p: _age(p)),
    ("Theo dõi", 10, lambda p: p.get("watchers")),
    ("Giá", 16, lambda p: p.get("price_text")),
    ("Ngày bán gần nhất", 16, lambda p: (p.get("last_sold_at") or "")[:10] or None),
    ("Giá bán gần nhất", 14, lambda p: p.get("last_sold_price_text")),
    ("Người bán", 18, lambda p: p.get("seller")),
    ("Danh mục", 40, lambda p: p.get("category")),
    ("Link eBay", 40, lambda p: p.get("item_url")),
    ("Item ID", 16, lambda p: p.get("item_id")),
]


def _age(product: dict):
    value = field_value(product, "start_age_days")
    return None if value is None else round(value, 1)


def export_tables(tables: list[tuple[str, list[dict]]], path: str | Path) -> Path:
    """Mỗi phần tử (tên sheet, danh sách sản phẩm) thành một sheet cùng bố cục cột."""
    path = Path(path)
    workbook = xlsxwriter.Workbook(str(path), {"strings_to_urls": False})
    header = workbook.add_format({"bold": True, "bg_color": "#1F3A5F", "font_color": "#FFFFFF", "border": 1,
                                  "valign": "vcenter"})
    wrap = workbook.add_format({"text_wrap": True, "valign": "top"})
    for name, products in tables:
        _write_sheet(workbook.add_worksheet(name[:31]), products, header, wrap)  # Excel giới hạn tên sheet 31 ký tự
    workbook.close()
    return path


def export_products(products: list[dict], path: str | Path, sheet_name: str = "Bestseller") -> Path:
    return export_tables([(sheet_name, products)], path)


def _write_sheet(sheet, products: list[dict], header, wrap) -> None:
    for col, (title, width, _) in enumerate(COLUMNS):
        sheet.write(0, col, title, header)
        sheet.set_column(col, col, width)
    for row, product in enumerate(products, start=1):
        for col, (title, _, getter) in enumerate(COLUMNS):
            value = getter(product)
            if value is None:
                continue
            if title in ("Hình ảnh", "Link eBay") and value:
                sheet.write_url(row, col, value, string=value)
            elif title == "Tiêu đề":
                sheet.write(row, col, value, wrap)
            else:
                sheet.write(row, col, value)

    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, max(1, len(products)), len(COLUMNS) - 1)
    sheet.write(len(products) + 2, 0, f"Xuất lúc {datetime.now():%Y-%m-%d %H:%M}")
