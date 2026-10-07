"""Gom dữ liệu cho trang Kết quả: mỗi sản phẩm một thẻ và số liệu cào về / đạt lọc theo từng từ khoá."""


def merge_keywords(rows: list[dict]) -> list[dict]:
    """Sản phẩm được nhiều từ khoá tìm thấy thành một thẻ ghi đủ các từ khoá; đạt lọc ở từ khoá nào thì tính là đạt."""
    merged: dict[str, dict] = {}
    for row in rows:
        existing = merged.get(row["item_id"])
        if existing is None:
            merged[row["item_id"]] = {**row, "kept": 1 if row.get("kept") else 0}
            continue
        if row["keyword"].lower() not in existing["keyword"].lower().split(", "):
            existing["keyword"] += ", " + row["keyword"]
        if row.get("kept"):
            existing["kept"] = 1
    return list(merged.values())


def keyword_summary(rows: list[dict], keywords: list[str] = ()) -> list[tuple[str, int, int]]:
    """[(từ khoá, số SP cào về, số SP đạt lọc)] theo thứ tự chữ cái.

    Từ khoá trong `keywords` (đang bật) mà chưa có sản phẩm nào vẫn được liệt kê với 0, để thấy ngay từ khoá nào
    chưa cào được gì.
    """
    counts: dict[str, list] = {}
    for keyword in keywords:
        counts.setdefault(keyword.lower(), [keyword, 0, 0])
    for row in rows:
        entry = counts.setdefault(row["keyword"].lower(), [row["keyword"], 0, 0])
        entry[1] += 1
        if row.get("kept"):
            entry[2] += 1
    return sorted(((name, found, kept) for name, found, kept in counts.values()), key=lambda t: t[0].lower())
