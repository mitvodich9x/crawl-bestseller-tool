"""watchcount.com client driven by a Playwright persistent browser profile.

The profile keeps the watchcount login cookie and the reCAPTCHA pass, so the user logs in once
(interactive_login) and scheduled scans reuse the session. Search pages embed their data as
`window.searchResult`.
"""
import json
import logging
import re
import time
from urllib.parse import parse_qsl, quote, unquote, urlsplit

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from app import browser_setup

log = logging.getLogger(__name__)

BASE_URL = "https://www.watchcount.com"
PAGE_SIZE = 20

# hai tab tìm kiếm của watchcount: /sold (sản phẩm đã có người mua) và /live (đang bán)
STATUS_OPTIONS = {
    "sold": "Search Sold (sản phẩm đã bán)",
    "live": "Search Live (sản phẩm đang bán)",
}
SORT_OPTIONS = {
    "bestmatch": "Best Match (lượt standard / ngày)",
    "price_asc": "Giá thấp → cao (lượt standard / ngày)",
    "price_desc": "Giá cao → thấp (lượt standard / ngày)",
    "listdate": "Newly Listed (lượt standard / ngày)",
    "watchcount": "Watch Count (lượt most-watched / ngày)",
    "bestselling": "Best Selling (lượt best-selling / tháng)",
}
# tab Sold chỉ cho sắp xếp theo Best Match và giá
SORTS_BY_STATUS = {
    "sold": ["bestmatch", "price_asc", "price_desc"],
    "live": list(SORT_OPTIONS),
}
# sort -> (params added to the URL, quota bucket)
_SORT_PARAMS = {
    "bestmatch": ({"sortBy": "bestmatch"}, "standard"),
    "price_asc": ({"sortBy": "price", "sortOrder": "asc"}, "standard"),
    "price_desc": ({"sortBy": "price", "sortOrder": "desc"}, "standard"),
    "listdate": ({"sortBy": "listdate", "sortOrder": "asc"}, "standard"),
    "watchcount": ({}, "most_watched"),  # site default, omitted from the URL
    "bestselling": ({"sortBy": "bestselling"}, "best_selling"),
}
# bộ lọc "Last sold date" của tab Sold
LAST_SOLD_OPTIONS = {
    "": "Không giới hạn", "1day": "1 ngày", "2days": "2 ngày", "3days": "3 ngày", "7days": "7 ngày",
    "14days": "14 ngày", "30days": "30 ngày", "45days": "45 ngày", "60days": "60 ngày",
}
# bộ lọc "Condition" (tình trạng hàng) của watchcount, dùng cho cả hai tab
CONDITIONS = {"": "Tất cả", "new": "New (hàng mới)", "used": "Used (hàng đã dùng)"}
# danh mục gốc của eBay US (cột trái trang kết quả watchcount), dạng {đoạn URL: tên}; danh mục con chỉ có qua dán link
CATEGORIES = {
    "": "Tất cả danh mục",
    "antiques_20081": "Antiques", "art_550": "Art", "baby_2984": "Baby",
    "books-magazines_267": "Books & Magazines", "business-industrial_12576": "Business & Industrial",
    "cameras-photo_625": "Cameras & Photo", "cell-phones-accessories_15032": "Cell Phones & Accessories",
    "clothing-shoes-accessories_11450": "Clothing, Shoes & Accessories", "coins-paper-money_11116": "Coins & Paper Money",
    "collectibles_1": "Collectibles", "computerstablets-networking_58058": "Computers/Tablets & Networking",
    "consumer-electronics_293": "Consumer Electronics", "crafts_14339": "Crafts", "dolls-bears_237": "Dolls & Bears",
    "ebay-motors_6000": "eBay Motors", "entertainment-memorabilia_45100": "Entertainment Memorabilia",
    "everything-else_99": "Everything Else", "gift-cards-coupons_172008": "Gift Cards & Coupons",
    "health-beauty_26395": "Health & Beauty", "home-garden_11700": "Home & Garden",
    "jewelry-watches_281": "Jewelry & Watches", "movies-tv_11232": "Movies & TV", "music_11233": "Music",
    "musical-instruments-gear_619": "Musical Instruments & Gear", "pet-supplies_1281": "Pet Supplies",
    "pottery-glass_870": "Pottery & Glass", "real-estate_10542": "Real Estate", "specialty-services_316": "Specialty Services",
    "sporting-goods_888": "Sporting Goods", "sports-mem-cards-fan-shop_64482": "Sports Mem, Cards & Fan Shop",
    "stamps_260": "Stamps", "tickets-experiences_1305": "Tickets & Experiences", "toys-hobbies_220": "Toys & Hobbies",
    "travel_3252": "Travel", "video-games-consoles_1249": "Video Games & Consoles",
}
_CATEGORY_RE = re.compile(r"^[a-z0-9-]*_\d+$")
LISTING_TYPES = {"fixedprice": "Fixed-Price / BIN", "all": "Tất cả", "auction": "Đấu giá", "bestoffer": "Best Offer"}
SITES = ["EBAY_US", "EBAY_GB", "EBAY_AU", "EBAY_CA", "EBAY_DE", "EBAY_FR", "EBAY_IT", "EBAY_ES"]

# values accepted by the startTimeFrom filter, in days
_START_WITHIN = [
    (1, "1day"), (2, "2days"), (3, "3days"), (4, "4days"), (5, "5days"), (6, "6days"), (7, "7days"),
    (14, "14days"), (30, "30days"), (60, "60days"), (90, "90days"), (180, "180days"), (365, "1year"),
    (730, "2years"), (1095, "3years"),
]

_BLOCK_MARKERS = ("just a moment", "access denied", "verify you are human", "unusual traffic")

# Trang xác minh reCAPTCHA. Script của trang tự chạy reCAPTCHA v3 rồi quay lại returnURL; trượt v3
# (hay gặp khi chạy ẩn) thì hiện ô "I'm not a robot" cần người tích. Qua rồi thì phiên nhớ lâu dài.
CHALLENGE_PATH = "/challenge"
CHALLENGE_AUTO_WAIT_S = 25
CHALLENGE_MANUAL_WAIT_S = 300
NEED_LOGIN_MESSAGE = ("Watchcount yêu cầu đăng nhập. Vào Cài đặt quét → "
                      "Đăng nhập watchcount rồi quét lại.")
CHALLENGE_MESSAGE = ("Watchcount yêu cầu xác minh reCAPTCHA. Trong cửa sổ trình duyệt, tích "
                     "\"I'm not a robot\" nếu được hỏi.")


# dải hướng dẫn chèn vào trang xác minh khi cửa sổ đang hiện: trang trắng ~15 giây trước khi ô tích xuất hiện
_CHALLENGE_BANNER_JS = """() => {
  if (document.getElementById('bc-guide')) return;
  const d = document.createElement('div');
  d.id = 'bc-guide';
  d.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;padding:14px 18px;' +
    'background:#1e3a8a;color:#fff;font:15px/1.5 Segoe UI,Arial,sans-serif;text-align:center';
  d.innerHTML = '<b>Bestseller Crawler cần bạn xác minh</b><br>' +
    'Chờ khoảng 15 giây cho ô <b>I&#39;m not a robot</b> hiện ra ở đầu trang, tích vào đó ' +
    '(chọn ảnh nếu được hỏi). Xong tool tự quét tiếp, không cần đóng cửa sổ.';
  document.body.appendChild(d);
}"""


def is_challenge_url(url: str | None) -> bool:
    return CHALLENGE_PATH in (url or "")


class WatchcountError(Exception):
    pass


class NeedLoginError(WatchcountError):
    pass


class BlockedError(WatchcountError):
    pass


class ChallengeError(BlockedError):
    """Kẹt ở trang /challenge: reCAPTCHA v3 không tự qua và chưa ai tích ô v2."""


def start_within_param(max_age_days: float | None) -> str | None:
    """Smallest startTimeFrom window that still contains every listing younger than max_age_days."""
    if max_age_days is None:
        return None
    for days, param in _START_WITHIN:
        if days >= max_age_days:
            return param
    return None


def _encode_segment(value: str) -> str:
    # mirrors the site's find_form.js
    return quote(value, safe="").replace("%20", "+").replace("%2F", "%252F")


def category_label(category: str) -> str:
    """Tên hiển thị của danh mục; danh mục con (từ link dán vào) thì dựng từ đoạn URL, vd home-decor_10033."""
    if category in CATEGORIES:
        return CATEGORIES[category]
    slug, _, cat_id = category.rpartition("_")
    return f"{slug.replace('-', ' ').title()} (#{cat_id})"


def valid_sort(status: str, sort_by: str) -> str:
    """Kiểu sắp xếp không có ở tab đang chọn thì về Best Match."""
    return sort_by if sort_by in SORTS_BY_STATUS.get(status, SORTS_BY_STATUS["live"]) else "bestmatch"


def build_search_url(keyword: str, site: str = "EBAY_US", sort_by: str = "bestmatch",
                     listing_type: str = "fixedprice", start_within: str | None = None, offset: int = 0,
                     *, status: str = "live", last_sold_within: str | None = None,
                     condition: str | None = None, category: str | None = None, min_price: float | None = None,
                     max_price: float | None = None, exact_match: bool = False,
                     extra_params: dict | None = None) -> str:
    status = status if status in STATUS_OPTIONS else "live"
    sort_params, _ = _SORT_PARAMS[valid_sort(status, sort_by)]
    # tham số lấy nguyên từ link dán vào (seller, freeShippingOnly, itemLocation...), không được đè các ô tool tự quản
    params = {k: v for k, v in (extra_params or {}).items() if k not in RESERVED_PARAMS and v not in (None, "")}
    params.update({"site": site, **sort_params})
    if status == "live" and start_within:  # tab Sold nhận tham số nhưng không lọc theo nó
        params["startTimeFrom"] = start_within
    if status == "sold" and last_sold_within:
        params["lastSoldDate"] = last_sold_within
    if condition:
        params["condition"] = condition
    if min_price:
        params["minPrice"] = f"{min_price:g}"
    if max_price:
        params["maxPrice"] = f"{max_price:g}"
    if exact_match:
        params["exactKeywordMatch"] = "true"
    if offset:
        params["offset"] = str(offset)
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items()))
    category = category if category and _CATEGORY_RE.match(category) else "-"
    return f"{BASE_URL}/{status}/{_encode_segment(keyword.strip() or '-')}/{category}/{listing_type}?{query}"


# các tham số tool tự dựng khi quét; phần còn lại của link dán vào được giữ trong extra_params
RESERVED_PARAMS = {"site", "sortBy", "sortOrder", "offset", "startTimeFrom", "lastSoldDate", "condition",
                   "minPrice", "maxPrice", "exactKeywordMatch"}
_SORT_FROM_LINK = {"bestmatch": "bestmatch", "listdate": "listdate", "watchcount": "watchcount",
                   "bestselling": "bestselling"}
_START_FROM_RE = re.compile(r"^(\d+)(hour|day|year)s?$")


def _start_days(value: str) -> float | None:
    match = _START_FROM_RE.match(value or "")
    if not match:
        return None
    count, unit = int(match.group(1)), match.group(2)
    return count / 24 if unit == "hour" else count * 365 if unit == "year" else count


def parse_search_url(url: str) -> dict:
    """Đọc link tìm kiếm của watchcount thành các ô cài đặt của tool. Link sai thì báo ValueError."""
    parts = urlsplit((url or "").strip())
    if "watchcount.com" not in parts.netloc.lower():
        raise ValueError("Đây không phải link của watchcount.com")
    segments = [seg for seg in parts.path.split("/") if seg]
    if len(segments) < 2 or segments[0] not in STATUS_OPTIONS:
        raise ValueError("Link phải là trang kết quả tìm kiếm, dạng watchcount.com/sold/<từ khoá>/... "
                         "hoặc watchcount.com/live/<từ khoá>/...")
    status = segments[0]
    keyword = unquote(segments[1].replace("+", " ")).replace("%2F", "/").strip()
    category = segments[2] if len(segments) > 2 and _CATEGORY_RE.match(segments[2]) else ""
    listing_type = segments[3] if len(segments) > 3 and segments[3] in LISTING_TYPES else "all"
    query = dict(parse_qsl(parts.query, keep_blank_values=False))
    notes = []

    sort_raw = query.get("sortBy")
    if sort_raw == "price":
        sort_by = "price_desc" if query.get("sortOrder") == "desc" else "price_asc"
    elif sort_raw is None:
        sort_by = "watchcount" if status == "live" else "bestmatch"  # mặc định của từng tab trên web
    elif sort_raw in _SORT_FROM_LINK:
        sort_by = _SORT_FROM_LINK[sort_raw]
    else:
        sort_by = "bestmatch"
        notes.append(f"Tool chưa có kiểu sắp xếp \"{sort_raw}\", dùng Best Match")
    if valid_sort(status, sort_by) != sort_by:
        notes.append(f"Tab Sold không sắp xếp được theo {SORT_OPTIONS[sort_by].split(' (')[0]}, dùng Best Match")
        sort_by = "bestmatch"

    site = query.get("site") or "EBAY_US"
    if site not in SITES:
        notes.append(f"Tool chưa có eBay site {site}, dùng EBAY_US")
        site = "EBAY_US"
    last_sold = query.get("lastSoldDate") or ""
    if last_sold not in LAST_SOLD_OPTIONS:
        notes.append(f"Tool chưa có \"Có đơn trong vòng\" = {last_sold}, để Không giới hạn")
        last_sold = ""
    condition = query.get("condition") or ""
    if condition not in CONDITIONS:
        notes.append(f"Tool chưa có Condition = {condition}, để Tất cả")
        condition = ""

    def price(key):
        try:
            value = float(query[key])
        except (KeyError, ValueError):
            return None
        return value if value > 0 else None

    start_days = _start_days(query.get("startTimeFrom", "")) if status == "live" else None
    return {
        "status": status,
        "keyword": "" if keyword == "-" else keyword,
        "category": category,
        "listing_type": listing_type,
        "sort_by": sort_by,
        "site": site,
        "last_sold_within": last_sold if status == "sold" else "",
        "condition": condition,
        "min_price": price("minPrice"),
        "max_price": price("maxPrice"),
        "exact_match": query.get("exactKeywordMatch", "").lower() == "true",
        "start_age_days": start_days,
        "extra_params": {k: v for k, v in query.items() if k not in RESERVED_PARAMS},
        "notes": notes,
    }


def quota_bucket(sort_by: str) -> str:
    return _SORT_PARAMS[sort_by][1]


def remaining_quota(usage: dict, sort_by: str) -> int | None:
    """Searches left today (this month for best selling). Handles user and guest usage payloads."""
    bucket = quota_bucket(sort_by)
    if bucket == "standard":
        limit = usage.get("max_daily_standard_searches", usage.get("max_standard"))
        used = usage.get("standard_count")
    elif bucket == "most_watched":
        limit = usage.get("max_daily_most_watched", usage.get("max_most_watched"))
        used = usage.get("most_watched_count")
    else:
        limit = usage.get("max_monthly_best_selling", usage.get("max_best_selling"))
        used = usage.get("best_selling_count")
    if limit is None or used is None:
        return None
    return max(0, int(limit) - int(used))


class WatchcountClient:
    def __init__(self, profile_dir, headless: bool = True):
        self.profile_dir = str(profile_dir)
        self.headless = headless
        self._pw: Playwright | None = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None

    # ---- lifecycle ------------------------------------------------------------------------

    def __enter__(self) -> "WatchcountClient":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def start(self) -> None:
        browser_setup.configure_env()
        self._pw = sync_playwright().start()
        try:
            self._launch()
        except Exception as exc:
            if "executable doesn't exist" not in str(exc).lower():
                raise
            # thiếu Chromium (máy mới, hoặc bản tải trước bị hỏng): tải lại rồi thử một lần nữa
            log.warning("Chromium chưa sẵn sàng, tải lại: %s", exc)
            ok, message = browser_setup.install_chromium()
            if not ok:
                raise WatchcountError(f"Không tải được trình duyệt Chromium: {message}") from exc
            self._launch()

    def _launch(self) -> None:
        self._ctx = self._pw.chromium.launch_persistent_context(
            self.profile_dir,
            headless=self.headless,
            locale="en-US",
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def close(self) -> None:
        for closer in (lambda: self._ctx and self._ctx.close(), lambda: self._pw and self._pw.stop()):
            try:
                closer()
            except Exception:  # browser may already be gone (user closed the window)
                pass
        self._ctx = self._pw = self._page = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise WatchcountError("Trình duyệt chưa được khởi động")
        return self._page

    # ---- account --------------------------------------------------------------------------

    def _ensure_on_site(self) -> None:
        if not self.page.url.startswith(BASE_URL):
            self.page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=60000)

    def is_logged_in(self) -> bool:
        self._ensure_on_site()
        return bool(self.page.evaluate("() => typeof IS_LOGGED_IN !== 'undefined' && IS_LOGGED_IN === true"))

    def account_status(self) -> dict:
        logged_in = self.is_logged_in()
        endpoint = "/user/usage" if logged_in else "/guest/usage"
        text = self.page.evaluate("u => fetch(u, {credentials: 'include'}).then(r => r.text())", endpoint)
        try:
            usage = json.loads(text).get("data") or {}
        except ValueError:
            usage = {}
        return {"logged_in": logged_in, "usage": usage}

    def interactive_login(self, timeout_s: int = 600, should_stop=lambda: False) -> bool:
        """Open the login page in a visible window and wait until the user has signed in."""
        if self.is_logged_in():
            return True
        self.page.goto(BASE_URL + "/login", wait_until="domcontentloaded", timeout=60000)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and not should_stop():
            try:
                if self.page.is_closed():
                    return False
                logged = self.page.evaluate(
                    "() => typeof IS_LOGGED_IN !== 'undefined' && IS_LOGGED_IN === true")
                if logged:
                    return True
            except Exception:
                pass  # page is navigating
            time.sleep(2)
        return False

    def pass_challenge(self, should_stop=lambda: False) -> None:
        """Mở một trang tìm kiếm để qua reCAPTCHA ngay trong cửa sổ đang hiện (tốn 1 lượt standard)."""
        self.search(build_search_url("t-shirt"), should_stop=should_stop)

    # ---- search ---------------------------------------------------------------------------

    def _bring_window_to_front(self) -> None:
        """Cửa sổ Chromium mở từ app hay nằm sau các cửa sổ khác; thu nhỏ rồi mở lại để Windows đưa nó lên trên."""
        try:
            session = self._ctx.new_cdp_session(self.page)
            window_id = session.send("Browser.getWindowForTarget")["windowId"]
            for state in ("minimized", "normal"):
                session.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": state}})
            self.page.bring_to_front()
        except Exception as exc:
            log.info("Không đưa được cửa sổ trình duyệt lên trên: %s", exc)

    def _wait_challenge(self, timeout_s: float, should_stop) -> bool:
        if not self.headless:
            self._bring_window_to_front()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and not should_stop():
            try:
                if self.page.is_closed():
                    return False
                if not is_challenge_url(self.page.url):
                    return True
                if not self.headless:
                    self.page.evaluate(_CHALLENGE_BANNER_JS)
            except Exception:
                pass  # page is navigating
            time.sleep(1)
        return False

    def search(self, url: str, timeout_ms: int = 45000, should_stop=lambda: False) -> dict:
        page = self.page
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if is_challenge_url(page.url):
            wait_s = CHALLENGE_AUTO_WAIT_S if self.headless else CHALLENGE_MANUAL_WAIT_S
            log.info("Gặp trang xác minh reCAPTCHA, chờ tối đa %ss", wait_s)
            if not self._wait_challenge(wait_s, should_stop):
                raise ChallengeError(CHALLENGE_MESSAGE)
        try:
            page.wait_for_function("() => window.searchResult !== undefined", timeout=timeout_ms)
        except PlaywrightTimeout as exc:
            title = (page.title() or "").lower()
            body = (page.content() or "")[:20000].lower()
            if any(marker in title or marker in body for marker in _BLOCK_MARKERS):
                raise BlockedError("Watchcount đang chặn hoặc yêu cầu xác minh (captcha)") from exc
            raise WatchcountError(f"Trang không trả dữ liệu tìm kiếm: {page.url}") from exc
        result = page.evaluate("() => window.searchResult") or {}
        error = result.get("error")
        if error and "auth" in str(error).lower():
            raise NeedLoginError(str(error))
        return result
