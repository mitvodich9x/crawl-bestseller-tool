"""Chụp ảnh minh hoạ cho trang Hướng dẫn (app/assets/guide/*.png) từ chính giao diện app.

Chạy: python tools/make_guide_images.py [--no-captcha] [--web]
App chạy ẩn trên một thư mục data tạm với dữ liệu mẫu (tools/guide_sample.json), không đụng tới
database, phiên đăng nhập hay autostart thật. Ảnh sản phẩm tải từ eBay nên cần mạng.
Ảnh trang xác minh reCAPTCHA chụp bằng Playwright với một profile trình duyệt mới.
--web: chụp khung tìm kiếm trên web watchcount bằng profile thật của app (data/browser_profile, phải đã qua
reCAPTCHA), mở cửa sổ trình duyệt và tốn 2 lượt standard.
"""
import copy
import json
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import autostart, paths  # noqa: E402

OUT = ROOT / "app" / "assets" / "guide"
REAL_PROFILE = ROOT / "data" / "browser_profile"  # lấy trước khi data_dir bị trỏ sang thư mục tạm
SAMPLE_LINK = ("https://www.watchcount.com/sold/Personalized+suncatcher/-/all"
               "?condition=new&lastSoldDate=30days&offset=60&site=EBAY_US&sortBy=bestmatch")
TMP = Path(tempfile.mkdtemp(prefix="bc_guide_"))
paths.data_dir = lambda: TMP  # mọi đường dẫn data của app trỏ vào thư mục tạm
autostart.set_enabled = lambda enabled: None  # không sửa autostart thật của máy

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QGroupBox, QWidget  # noqa: E402

from app import config  # noqa: E402
from app.core import filters  # noqa: E402
from app.db.database import Database  # noqa: E402
from app.scraper.parsing import parse_item  # noqa: E402
from app.ui.style import STYLESHEET, app_icon  # noqa: E402

KEYWORDS = ["halloween doormat", "funny shirt", "cat mug", "christmas ornament"]


def pump(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.02)


def save(widget: QWidget, name: str) -> None:
    pump(0.3)
    widget.grab().save(str(OUT / name))
    print("  ", name)


def group(page: QWidget, title_start: str) -> QGroupBox:
    return next(box for box in page.findChildren(QGroupBox) if box.title().startswith(title_start))


def seed(db: Database, cfg: dict) -> None:
    db.add_keywords(KEYWORDS)
    rows = json.loads((ROOT / "tools" / "guide_sample.json").read_text(encoding="utf-8"))
    rules = filters.rules_from_config(cfg["scan_filters"])
    run_id = db.start_run("manual")
    products = [parse_item(r) for r in rows]
    kept = {p["item_id"] for p in filters.apply(products, rules)}
    db.save_products(run_id, "halloween doormat", products, kept)
    db.finish_run(run_id, "completed", len(products), len(kept), 1, None)


def shoot_app() -> None:
    from app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())

    cfg = config.load()
    cfg["state"]["last_run_date"] = date.today().isoformat()  # để lịch không tự quét trong lúc chụp
    db = Database()
    seed(db, cfg)

    win = MainWindow(db, cfg)
    win._schedule_timer.stop()
    win.tray.hide()
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    win.resize(1320, 860)
    win.show()

    # 1. Kết quả: chờ ảnh sản phẩm tải xong
    win.nav.setCurrentRow(0)
    for _ in range(300):
        pump(0.1)
        waiting = [label for label in win.results_page.findChildren(QWidget)
                   if getattr(label, "text", None) and callable(label.text) and label.text() == "Đang tải ảnh..."]
        if not waiting:
            break
    save(win, "results.png")
    from app.ui.widgets.product_card import ProductCard
    # lấy thẻ đang hiện và đã có ảnh (thẻ cũ của lần vẽ trước có thể chưa kịp xoá)
    cards = [c for c in win.results_page.findChildren(ProductCard)
             if c.isVisible() and c.image.pixmap() is not None and not c.image.pixmap().isNull()]
    if cards:
        save(cards[0], "card.png")

    # 2. Từ khoá
    win.nav.setCurrentRow(1)
    save(win, "keywords.png")

    # 3. Cài đặt quét
    win.nav.setCurrentRow(2)
    settings = win.settings_page
    settings.account_label.setText(
        "✅ Đã đăng nhập: ban@example.com — gói Free\nStandard / ngày: còn 188\n"
        "Watch Count / ngày: còn 50\nBest Selling / tháng: còn 3")
    save(group(settings, "Tài khoản"), "settings_account.png")
    save(group(settings, "Tìm kiếm"), "settings_search.png")
    save(group(settings, "Bộ lọc"), "settings_filters.png")
    save(group(settings, "Chung"), "settings_general.png")

    # 3b. Dán link mẫu ở mục "Cào giống một link watchcount" của trang Hướng dẫn
    from app.scraper import watchcount

    saved = copy.deepcopy(settings.cfg)
    settings.link_input.setText(SAMPLE_LINK)
    settings.link_input.setCursorPosition(0)
    save(group(settings, "Dán link"), "paste_link.png")
    parsed = watchcount.parse_search_url(SAMPLE_LINK)
    box = settings.link_confirm_box(parsed)
    box.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    box.show()
    save(box, "link_confirm.png")
    box.close()
    settings.apply_parsed_link(parsed, clear_filters=True)
    settings.max_pages.setValue(10)
    settings.take_all_pages.setChecked(True)
    settings.link_input.clear()
    save(group(settings, "Tìm kiếm"), "link_search.png")
    save(group(settings, "Bộ lọc"), "link_filters.png")
    settings.cfg.clear()
    settings.cfg.update(saved)
    settings.load_from_config()

    # 4. Lịch quét
    win.nav.setCurrentRow(3)
    save(win, "schedule.png")

    # 5. Đang quét: thanh trên cùng
    win.nav.setCurrentRow(0)
    win.status_label.setText("Đang quét 'halloween doormat' (1/4)")
    win.progress.setRange(0, 4)
    win.progress.setValue(1)
    win.progress.setVisible(True)
    win.scan_btn.setEnabled(False)
    win.stop_btn.setEnabled(True)
    pump(0.3)
    top = win.status_label.parentWidget()
    save(top, "topbar_scanning.png")

    # 6. Nhật ký
    for line in ("Bắt đầu quét (thủ công)", "Đang mở trình duyệt... (tab Sold)",
                 "Lượt tìm kiếm còn lại (standard): 188",
                 "[1/4] 'halloween doormat' — tối đa 10 trang",
                 "   trang 1: 20 sản phẩm (20 mới), 6 đạt bộ lọc (tổng kết quả: 69)",
                 "Kết thúc (completed): 69 sản phẩm, 14 đạt bộ lọc, dùng 4 lượt",
                 "   halloween doormat: 69 sản phẩm, 14 đạt bộ lọc"):
        win._log(line)
    win.nav.setCurrentRow(4)
    save(win, "log.png")

    # 6b. Nhật ký của lần quét khớp link mẫu (số liệu thật, quét ngày 2026-10-05)
    win.log_page.text.clear()
    link = ("https://www.watchcount.com/sold/Personalized+suncatcher/-/all"
            "?condition=new&lastSoldDate=30days&site=EBAY_US&sortBy=bestmatch")
    for line in ["Bắt đầu quét (thủ công)", "Đang mở trình duyệt... (tab Sold)",
                 "Lượt tìm kiếm còn lại (standard): 188",
                 "[1/1] 'Personalized suncatcher' — tối đa 10 trang",
                 f"   link trang 1: {link}",
                 "   trang 1: 20 sản phẩm (20 mới), 20 đạt bộ lọc (tổng kết quả: 165)",
                 "   trang 2: 20 sản phẩm (20 mới), 20 đạt bộ lọc (tổng kết quả: 165)",
                 "   trang 3: 20 sản phẩm (20 mới), 20 đạt bộ lọc (tổng kết quả: 164)",
                 "   trang 4: 20 sản phẩm (19 mới), 20 đạt bộ lọc (tổng kết quả: 164)",
                 "   ...",
                 "   trang 9: 11 sản phẩm (10 mới), 11 đạt bộ lọc (tổng kết quả: 165)",
                 "Kết thúc (completed): 167 sản phẩm, 167 đạt bộ lọc, dùng 9 lượt",
                 "   Personalized suncatcher: 167 sản phẩm, 167 đạt bộ lọc"]:
        win._log(line)
    win.log_page.text.setFixedSize(1000, 235)
    save(win.log_page.text, "link_log.png")
    win.tray.hide()
    win.close()


def shoot_captcha() -> None:
    """Trang xác minh với dải hướng dẫn của app, như người dùng sẽ thấy."""
    from app.scraper import watchcount

    client = watchcount.WatchcountClient(TMP / "captcha_profile", headless=True)
    client.start()
    try:
        page = client.page
        page.set_viewport_size({"width": 1100, "height": 560})
        page.goto(watchcount.build_search_url("t-shirt", status="sold"), wait_until="domcontentloaded")
        # trình duyệt ẩn luôn trượt reCAPTCHA v3 -> ô "I'm not a robot" hiện sau ~15 giây
        page.wait_for_selector("#challenge-section[style*='block'] iframe[title='reCAPTCHA']", timeout=60000)
        pump(3)
        # profile mới: watchcount hiện hộp "Time Zone Updated" che mất ô tích
        ok = page.locator(".modal.show button", has_text="OK")
        if ok.count():
            ok.first.click()
            pump(1)
        page.evaluate(watchcount._CHALLENGE_BANNER_JS)
        page.screenshot(path=str(OUT / "captcha.png"))
        print("   captcha.png")
    finally:
        client.close()


def shoot_web() -> None:
    """Khung tìm kiếm trên web watchcount (tab Sold, tab Live, bảng Additional Filters)."""
    from app.scraper import watchcount

    client = watchcount.WatchcountClient(REAL_PROFILE, headless=False)
    client.start()
    try:
        page = client.page
        page.set_viewport_size({"width": 1400, "height": 1000})
        live_link = SAMPLE_LINK.replace("/sold/", "/live/").replace("lastSoldDate=30days&offset=60&", "")
        for link, name in ((SAMPLE_LINK, "web_form_sold.png"), (live_link, "web_form_live.png")):
            client.search(link)
            page.wait_for_timeout(1500)
            ok = page.locator(".modal.show button", has_text="OK")  # hộp "Time Zone Updated"
            if ok.count():
                ok.first.click()
            page.locator("[href='#sfilter-container'], [data-bs-target='#sfilter-container']").first.click()
            page.wait_for_timeout(1200)
            page.locator("#sfilter-container").screenshot(path=str(OUT / name))
            print("  ", name)
        page.locator("a#additional-filter-button").click()
        page.wait_for_timeout(1200)
        # chụp tới hết nút Reset, bỏ phần trắng bên dưới
        panel = page.locator("#additional-filters-offcanvas").bounding_box()
        bottom = page.locator("#additional-filters-offcanvas button", has_text="Reset").last.bounding_box()
        clip = {**panel, "height": bottom["y"] + bottom["height"] + 24 - panel["y"]}
        page.screenshot(path=str(OUT / "web_more_filters.png"), clip=clip)
        print("   web_more_filters.png")
    finally:
        client.close()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Thư mục data tạm: {TMP}")
    shoot_app()
    if "--no-captcha" not in sys.argv:
        shoot_captcha()
    if "--web" in sys.argv:
        shoot_web()
    return 0


if __name__ == "__main__":
    sys.exit(main())
