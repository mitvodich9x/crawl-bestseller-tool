"""One scan: for each keyword, page through watchcount, store every item, mark the ones passing the filters."""
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Callable

from app.core import filters
from app.db.database import Database
from app.paths import browser_profile_dir
from app.scraper import watchcount
from app.scraper.parsing import parse_item

log = logging.getLogger(__name__)


@dataclass
class ScanCallbacks:
    log: Callable[[str], None] = lambda msg: None
    progress: Callable[[int, int, str], None] = lambda done, total, keyword: None
    should_stop: Callable[[], bool] = lambda: False


@dataclass
class ScanSummary:
    run_id: int
    status: str = "running"
    total_found: int = 0
    total_kept: int = 0
    pages_used: int = 0
    error: str | None = None
    per_keyword: dict = field(default_factory=dict)


def _max_start_age(rules: list[filters.FilterRule]) -> float | None:
    for rule in rules:
        if rule.field == "start_age_days" and rule.active and rule.op in ("<", "<="):
            return rule.value
    return None


def _sleep(seconds: float, should_stop: Callable[[], bool]) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end and not should_stop():
        time.sleep(0.2)


def run_scan(db: Database, cfg: dict, keywords: list[str], trigger: str,
             cb: ScanCallbacks | None = None, client_factory=None) -> ScanSummary:
    cb = cb or ScanCallbacks()
    search_cfg = cfg["search"]
    rules = filters.rules_from_config(cfg["scan_filters"])
    sort_by = search_cfg["sort_by"]
    max_pages = max(1, int(search_cfg["max_pages"]))
    stop_after_empty = int(search_cfg["stop_after_empty_pages"])  # 0 = quét hết trang, không dừng sớm
    start_within = watchcount.start_within_param(_max_start_age(rules))

    summary = ScanSummary(run_id=db.start_run(trigger))

    def say(msg: str) -> None:
        log.info(msg)
        cb.log(msg)

    if not keywords:
        summary.status, summary.error = "failed", "Chưa có từ khoá nào được bật"
        say(summary.error)
        db.finish_run(summary.run_id, summary.status, 0, 0, 0, summary.error)
        return summary

    factory = client_factory or (lambda: watchcount.WatchcountClient(browser_profile_dir(), search_cfg["headless"]))
    client = factory()
    try:
        say("Đang mở trình duyệt...")
        client.start()
        account = client.account_status()
        remaining = watchcount.remaining_quota(account["usage"], sort_by)
        if not account["logged_in"]:
            say("⚠ Chưa đăng nhập watchcount: dùng hạn mức khách (ít lượt hơn). Vào Cài đặt để đăng nhập.")
        if remaining is None:
            say("Không đọc được hạn mức, quét tối đa theo cấu hình")
            remaining = len(keywords) * max_pages
        else:
            remaining = max(0, remaining - int(search_cfg.get("reserve_quota") or 0))
            say(f"Lượt tìm kiếm còn lại ({watchcount.quota_bucket(sort_by)}): {remaining}")

        total_keywords = len(keywords)
        for index, keyword in enumerate(keywords):
            if cb.should_stop():
                summary.status = "stopped"
                break
            if remaining <= 0:
                summary.status = "quota_exhausted"
                say("Hết lượt tìm kiếm của watchcount, dừng quét")
                break

            # spread what is left across the remaining keywords so the last ones are not starved
            budget = min(max_pages, max(1, remaining // (total_keywords - index)))
            cb.progress(index, total_keywords, keyword)
            say(f"[{index + 1}/{total_keywords}] '{keyword}' — tối đa {budget} trang")

            # watchcount repeats items across pages (the result set shifts while paging),
            # so count each item once per keyword
            seen_ids: set[str] = set()
            kept_ids_all: set[str] = set()
            empty_streak = 0
            offset = 0
            for page_no in range(budget):
                if cb.should_stop() or remaining <= 0:
                    break
                url = watchcount.build_search_url(keyword, search_cfg["site"], sort_by,
                                                  search_cfg["listing_type"], start_within, offset)
                result = _search_with_retry(client, url, say, cb.should_stop)
                remaining -= 1
                summary.pages_used += 1
                if result is None:
                    break

                products = [parse_item(raw) for raw in (result.get("items") or []) if raw.get("id")]
                kept_ids = {p["item_id"] for p in filters.apply(products, rules)}
                if products:
                    db.save_products(summary.run_id, keyword, products, kept_ids)
                new_ids = {p["item_id"] for p in products} - seen_ids
                seen_ids |= new_ids
                kept_ids_all |= kept_ids
                say(f"   trang {page_no + 1}: {len(products)} sản phẩm ({len(new_ids)} mới), "
                    f"{len(kept_ids)} đạt bộ lọc (tổng kết quả: {result.get('total')})")

                empty_streak = 0 if any(p["total_sold"] > 0 for p in products) else empty_streak + 1
                if not products or result.get("nextOffset") is None:
                    break
                if 0 < stop_after_empty <= empty_streak:
                    say(f"   {empty_streak} trang liền không có đơn nào, chuyển từ khoá")
                    break
                offset = int(result["nextOffset"])
                _sleep(random.uniform(search_cfg["delay_min"], search_cfg["delay_max"]), cb.should_stop)

            summary.per_keyword[keyword] = {"found": len(seen_ids), "kept": len(kept_ids_all)}
            summary.total_found += len(seen_ids)
            summary.total_kept += len(kept_ids_all)
            if index + 1 < total_keywords:
                _sleep(random.uniform(search_cfg["delay_min"], search_cfg["delay_max"]), cb.should_stop)

        cb.progress(total_keywords, total_keywords, "")
        if summary.status == "running":
            summary.status = "stopped" if cb.should_stop() else "completed"
    except watchcount.NeedLoginError:
        summary.status, summary.error = "need_login", "Watchcount yêu cầu đăng nhập cho kiểu sắp xếp này"
        say(summary.error)
    except watchcount.BlockedError as exc:
        summary.status, summary.error = "blocked", f"{exc}. Thử tắt chế độ ẩn trình duyệt rồi quét lại."
        say(summary.error)
    except Exception as exc:  # keep the app alive and record the failure
        log.exception("Scan failed")
        summary.status, summary.error = "failed", str(exc)
        say(f"Lỗi: {exc}")
    finally:
        client.close()
        db.finish_run(summary.run_id, summary.status, summary.total_found, summary.total_kept,
                      summary.pages_used, summary.error)

    say(f"Kết thúc ({summary.status}): {summary.total_found} sản phẩm, {summary.total_kept} đạt bộ lọc, "
        f"dùng {summary.pages_used} lượt")
    return summary


def _search_with_retry(client, url: str, say, should_stop, attempts: int = 3) -> dict | None:
    for attempt in range(1, attempts + 1):
        try:
            return client.search(url)
        except (watchcount.NeedLoginError, watchcount.BlockedError):
            raise
        except Exception as exc:
            say(f"   lỗi tải trang (lần {attempt}/{attempts}): {exc}")
            if attempt == attempts or should_stop():
                return None
            _sleep(5 * attempt, should_stop)
    return None
