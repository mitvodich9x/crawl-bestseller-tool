"""beta.watchcount.com client driven by a Playwright persistent browser profile.

The profile keeps the watchcount login cookie, so the user logs in once (interactive_login) and
scheduled scans reuse the session. Search pages embed their data as `window.searchResult`.
"""
import json
import logging
import time
from urllib.parse import quote

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

log = logging.getLogger(__name__)

BASE_URL = "https://beta.watchcount.com"
PAGE_SIZE = 20

SORT_OPTIONS = {
    "bestmatch": "Best Match (lượt standard / ngày)",
    "listdate": "Newly Listed (lượt standard / ngày)",
    "watchcount": "Watch Count (lượt most-watched / ngày)",
    "bestselling": "Best Selling (lượt best-selling / tháng)",
}
# sort -> (params added to the URL, quota bucket)
_SORT_PARAMS = {
    "bestmatch": ({"sortBy": "bestmatch"}, "standard"),
    "listdate": ({"sortBy": "listdate", "sortOrder": "asc"}, "standard"),
    "watchcount": ({}, "most_watched"),  # site default, omitted from the URL
    "bestselling": ({"sortBy": "bestselling"}, "best_selling"),
}
LISTING_TYPES = {"fixedprice": "Fixed-Price / BIN", "all": "Tất cả", "auction": "Đấu giá", "bestoffer": "Best Offer"}
SITES = ["EBAY_US", "EBAY_GB", "EBAY_AU", "EBAY_CA", "EBAY_DE", "EBAY_FR", "EBAY_IT", "EBAY_ES"]

# values accepted by the startTimeFrom filter, in days
_START_WITHIN = [
    (1, "1day"), (2, "2days"), (3, "3days"), (4, "4days"), (5, "5days"), (6, "6days"), (7, "7days"),
    (14, "14days"), (30, "30days"), (60, "60days"), (90, "90days"), (180, "180days"), (365, "1year"),
    (730, "2years"), (1095, "3years"),
]

_BLOCK_MARKERS = ("just a moment", "access denied", "verify you are human", "unusual traffic")


class WatchcountError(Exception):
    pass


class NeedLoginError(WatchcountError):
    pass


class BlockedError(WatchcountError):
    pass


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


def build_search_url(keyword: str, site: str = "EBAY_US", sort_by: str = "bestmatch",
                     listing_type: str = "fixedprice", start_within: str | None = None, offset: int = 0) -> str:
    sort_params, _ = _SORT_PARAMS[sort_by]
    params = {"site": site, **sort_params}
    if start_within:
        params["startTimeFrom"] = start_within
    if offset:
        params["offset"] = str(offset)
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items()))
    return f"{BASE_URL}/live/{_encode_segment(keyword.strip() or '-')}/-/{listing_type}?{query}"


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
        self._pw = sync_playwright().start()
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

    # ---- search ---------------------------------------------------------------------------

    def search(self, url: str, timeout_ms: int = 45000) -> dict:
        page = self.page
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
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
