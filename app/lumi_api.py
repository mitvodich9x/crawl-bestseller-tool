"""Đẩy sản phẩm trend lên web Lumi (lumi-node): POST /api/scanner/competitors/trends.

Xác thực bằng Token API quyền "Tool Scanner" tạo ở Lumi (Hệ thống → Token API), gắn với tài khoản admin hoặc
quản lý kênh. Lumi gộp theo item_id: đẩy lại cùng sản phẩm thì cập nhật số liệu, không tạo trùng.
"""
import json
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://app.lumihubs.com"
PUSH_PATH = "/api/scanner/competitors/trends"
BATCH_SIZE = 500  # Lumi nhận tối đa 500 sản phẩm mỗi lần


class LumiError(Exception):
    pass


def normalize_base_url(url: str | None) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        return DEFAULT_BASE_URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.removesuffix("/api")


def _text(value, limit: int) -> str | None:
    value = (value or "").strip() if isinstance(value, str) else value
    return str(value)[:limit] if value else None


def _number(value) -> float | None:
    return value if isinstance(value, (int, float)) and value >= 0 else None


def item_payload(product: dict) -> dict:
    """Sản phẩm trong tool -> phần tử `items` Lumi nhận."""
    total_sold, watchers = _number(product.get("total_sold")), _number(product.get("watchers"))
    return {
        "item_id": str(product["item_id"]),
        "title": _text(product.get("title"), 500) or str(product["item_id"]),
        "image_url": _text(product.get("image_url"), 1000),
        "item_url": _text(product.get("item_url"), 1000),
        "keyword": _text(product.get("keyword"), 200),
        "price": _number(product.get("price")),
        "currency": _text(product.get("currency"), 10),
        "total_sold": int(total_sold) if total_sold is not None else None,
        "days_per_sale": _number(product.get("days_per_sale")),
        "watchers": int(watchers) if watchers is not None else None,
        "start_time": product.get("start_time") or None,
        "last_sold_at": product.get("last_sold_at") or None,
        "seller": _text(product.get("seller"), 200),
        "category": _text(product.get("category"), 300),
    }


def _post(base_url: str, token: str, body: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        normalize_base_url(base_url) + PUSH_PATH,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": "BestsellerCrawler"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except ValueError:
            data = {}
        message = data.get("message") or data.get("error") or f"Lumi trả lỗi HTTP {exc.code}"
        if exc.code == 401:
            message = "Token Lumi không đúng hoặc đã bị thu hồi."
        raise LumiError(message) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LumiError(f"Không kết nối được Lumi ({normalize_base_url(base_url)}): {exc}") from exc


def push_trends(base_url: str, token: str, products: list[dict], timeout: int = 30) -> dict:
    """Đẩy theo lô; trả {"created": n, "updated": n}."""
    if not (token or "").strip():
        raise LumiError("Chưa nhập Token Lumi (Cài đặt quét → Lumi).")
    result = {"created": 0, "updated": 0}
    items = [item_payload(p) for p in products]
    for start in range(0, len(items), BATCH_SIZE):
        data = _post(base_url, token.strip(), {"items": items[start:start + BATCH_SIZE]}, timeout)
        result["created"] += int(data.get("created") or 0)
        result["updated"] += int(data.get("updated") or 0)
    return result
