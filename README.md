# Bestseller Crawler

Tool desktop quét sản phẩm eBay bán chạy trên [watchcount.com](https://beta.watchcount.com) theo danh sách từ khoá. Tool lọc theo start date, tổng đơn và tốc độ bán (sell one), hiển thị kết quả dạng card, xuất Excel và tự quét theo lịch.

## Chạy
```
pip install -r requirements.txt
run.bat            (hoặc: python main.py)
```
Lần đầu tool tự tải Chromium cho Playwright (~200MB).

## Sử dụng
1. **Cài đặt quét**: bấm *Đăng nhập watchcount*, đăng nhập trong cửa sổ trình duyệt vừa mở, rồi *Kiểm tra tài khoản* để xem số lượt còn lại. Tool không lưu mật khẩu; phiên đăng nhập nằm trong `data/browser_profile`.
2. **Từ khoá**: dán mỗi dòng một từ khoá, bật/tắt từng từ khoá.
3. **Cài đặt quét → Bộ lọc khi quét**. Để trống ô nào thì không lọc theo ô đó.
   - *Start ≤ 7*: bỏ listing đăng quá 7 ngày. Điều kiện này cũng được gửi lên watchcount để tiết kiệm lượt.
   - *Sell one ≤ 7 / 3 / 1*: số ngày trung bình bán được 1 đơn, lấy từ trường "sold/day | week | month" của watchcount.
   - *Tổng đơn*, *lượt theo dõi*, *giá*: tuỳ chọn.
4. **Lịch quét**: mỗi N ngày, ngày lẻ hoặc ngày chẵn, kèm giờ quét. App phải đang chạy; đóng cửa sổ thì app thu xuống khay hệ thống. Có thể bật *Khởi động cùng Windows*.
5. **Kết quả**: lọc theo từ khoá, lần quét, bộ lọc nâng cao; sắp xếp; *Xuất Excel* với các cột Từ khoá | Tiêu đề | Hình ảnh | thông số.

## Hạn mức watchcount
Mỗi trang kết quả (20 sản phẩm) tính là 1 lượt.

| Gói | Standard (Best Match) | Watch Count | Best Selling |
|---|---|---|---|
| Free | 200 / ngày | 50 / ngày | 3 / tháng |

Tool mặc định dùng **Best Match** (lượt standard) và tự lọc/xếp theo số đơn. Số lượt còn lại được chia đều cho các từ khoá.

Muốn lấy **toàn bộ sản phẩm** của một từ khoá (vd "doormat halloween" ra ~1000 SP = ~50 trang):
- *Số trang tối đa / từ khoá*: đặt 50 (tối đa 500).
- Tích **Lấy hết các trang** để tool không dừng sớm ở những trang không có sản phẩm nào có đơn.

Nếu để mặc định (dừng sau 3 trang liền không có đơn), tool quét nhanh hơn và tốn ít lượt, nhưng có thể bỏ sót sản phẩm nằm sâu phía sau.

Chi tiết kỹ thuật về watchcount: [docs/watchcount-recon.md](docs/watchcount-recon.md).

## Cấu trúc
```
main.py                  entry: single instance, tray, excepthook
app/config.py            data/settings.json
app/db/database.py       data/bestseller.db (keywords, scan_runs, products, product_keywords, snapshots)
app/scraper/watchcount.py  URL, quota, Playwright client (đọc window.searchResult)
app/scraper/parsing.py   item watchcount -> bản ghi sản phẩm
app/core/filters.py      bộ lọc (field, op, value)
app/core/scheduler.py    tính ngày/giờ quét
app/core/scan_job.py     điều phối 1 lần quét
app/ui/                  PyQt6: main_window, pages/, widgets/, workers.py
tests/                   pytest
```

## Test
```
python -m pytest tests
```

## Cập nhật phiên bản
App tự kiểm tra bản mới trên GitHub Releases mỗi lần mở, và có nút **Kiểm tra cập nhật** trong *Cài đặt quét*.
Khi đồng ý, app tải file zip của bản mới, giải nén rồi một script phụ chờ app thoát, ghi đè file và mở lại app.
Thư mục `data` (database, cài đặt, phiên đăng nhập watchcount) được giữ nguyên.

Phát hành bản mới:
1. Tăng `APP_VERSION` trong [app/app_version.py](app/app_version.py).
2. `build.bat`
3. Tạo release trên GitHub với tag `vX.Y.Z` và đính kèm file zip trong `release/`.

## Build bản chạy độc lập (.exe)
```
build.bat
```
Script tạo icon, chạy test, build PyInstaller one-folder rồi nén thành `release\BestsellerCrawler-<version>.zip`.
Người dùng cuối giải nén ở đâu cũng được rồi chạy `BestsellerCrawler.exe`; dữ liệu nằm trong thư mục `data` cạnh file exe.
Đổi số phiên bản trong [app/app_version.py](app/app_version.py) trước khi build bản phát hành mới.
