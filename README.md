# Bestseller Crawler

Tool desktop quét sản phẩm eBay bán chạy trên [watchcount.com](https://www.watchcount.com) theo danh sách từ khoá. Tool lọc theo start date, tổng đơn và tốc độ bán (sell one), hiển thị kết quả dạng card, xuất Excel và tự quét theo lịch.

## Chạy
```
pip install -r requirements.txt
run.bat            (hoặc: python main.py)
```
Lần đầu tool tự tải Chromium cho Playwright (~200MB).

## Sử dụng
Hướng dẫn đầy đủ, có ảnh minh hoạ, nằm ngay trong app: mục **📖 Hướng dẫn** ở thanh bên trái (mở sẵn khi chưa có từ khoá nào).
Nội dung ở [app/assets/guide/guide.html](app/assets/guide/guide.html). Ảnh chụp lại bằng
`python tools/make_guide_images.py` (chạy app ẩn với dữ liệu mẫu, cần mạng để tải ảnh sản phẩm).

1. **Cài đặt quét**: bấm *Đăng nhập watchcount*, đăng nhập trong cửa sổ trình duyệt vừa mở, rồi *Kiểm tra tài khoản* để xem số lượt còn lại. Tool không lưu mật khẩu; phiên đăng nhập nằm trong `data/browser_profile`.
2. **Từ khoá**: dán mỗi dòng một từ khoá, bật/tắt từng từ khoá.
   **Tab tìm kiếm** (Cài đặt quét): mặc định **Search Sold** (chỉ listing đã có đơn, kèm ngày/giá bán gần nhất,
   lọc "có đơn trong vòng N ngày"); **Search Live** để dùng Watch Count / Newly Listed / Best Selling.
3. **Cài đặt quét → Bộ lọc khi quét**. Để trống ô nào thì không lọc theo ô đó.
   - *Start ≤ 7*: bỏ listing đăng quá 7 ngày. Điều kiện này cũng được gửi lên watchcount để tiết kiệm lượt.
   - *Sell one ≤ 7 / 3 / 1*: số ngày trung bình bán được 1 đơn, lấy từ trường "sold/day | week | month" của watchcount.
   - *Tổng đơn*, *lượt theo dõi*, *giá*: tuỳ chọn.
4. **Lịch quét**: mỗi N ngày, ngày lẻ hoặc ngày chẵn, kèm giờ quét. App phải đang chạy; đóng cửa sổ thì app thu xuống khay hệ thống. Có thể bật *Khởi động cùng Windows*.
5. **Kết quả**: hai bảng — *Bảng 1 · Tất cả SP cào về* (gộp theo từ khoá, kèm dòng thống kê mỗi từ khoá cào về / đạt lọc
   bao nhiêu) và *Bảng 2 · SP đạt bộ lọc*. Lọc theo từ khoá, lần quét, bộ lọc nâng cao; sắp xếp; *Xuất Excel* ra 2 sheet
   (1. Cào về, 2. Đạt bộ lọc) với các cột Từ khoá | Tiêu đề | Hình ảnh | thông số; *Xoá kết quả* xoá phần đang xem.

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

## Khi app báo lỗi trên máy người dùng
- **"Chưa tải được trình duyệt Chromium"**: mở `BestsellerCrawler.exe --selftest-browser` (chạy trong cmd tại
  thư mục app). Lệnh này in ra thư mục trình duyệt, tự tải nếu thiếu, và ghi kết quả vào `data\logs\selftest.txt`.
- **"Watchcount yêu cầu xác minh reCAPTCHA"**: watchcount đẩy sang trang `/challenge` (reCAPTCHA), không phải
  do mất đăng nhập. Trình duyệt ẩn hay bị chấm trượt, nên app tự mở cửa sổ trình duyệt; tích *I'm not a robot*
  nếu được hỏi. Qua một lần thì phiên được nhớ và các lần quét sau lại chạy ẩn.
- **"Watchcount yêu cầu đăng nhập"**: chỉ gặp khi quét *Best Selling* mà chưa đăng nhập. Các kiểu sắp xếp khác
  vẫn quét được bằng lượt của khách (20 lượt/ngày), nhưng nên đăng nhập để có 200 lượt/ngày.
- Từ 09/2026 `beta.watchcount.com` đã chuyển hẳn sang `www.watchcount.com`. Phiên đăng nhập cũ nằm ở tên miền
  beta nên không dùng được nữa: đăng nhập lại một lần trong *Cài đặt quét*.
- App luôn tự đặt `PLAYWRIGHT_BROWSERS_PATH` về `%LOCALAPPDATA%\ms-playwright`, nên máy có sẵn biến này
  của tool khác (nhất là giá trị `0`) vẫn chạy bình thường.

## Cài đặt trên máy người dùng
Chạy `BestsellerCrawlerSetup-<version>.exe` (giống Walmart Scanner Pro). Bộ cài không cần quyền admin, cài vào
`%LOCALAPPDATA%\Programs\BestsellerCrawler`, tạo shortcut Start Menu và Desktop. Dữ liệu nằm trong thư mục `data`
cạnh file exe; gỡ cài đặt hoặc cài bản mới đều giữ nguyên thư mục này.

## Cập nhật phiên bản
App tự kiểm tra bản mới trên GitHub Releases mỗi lần mở, và có nút **Kiểm tra cập nhật** trong *Cài đặt quét*.
Khi đồng ý, app tải file cài đặt của bản mới, thoát ra, chạy bộ cài ở chế độ im lặng vào đúng thư mục đang dùng
rồi tự mở lại. Release cũ chỉ có zip thì app giải nén và ghi đè bằng script phụ như trước.
Thư mục `data` (database, cài đặt, phiên đăng nhập watchcount) được giữ nguyên.

Phát hành bản mới:
1. Tăng `APP_VERSION` trong [app/app_version.py](app/app_version.py).
2. `build_installer.bat` (cần [Inno Setup 6](https://jrsoftware.org/isdl.php)).
3. Tạo release trên GitHub với tag `vX.Y.Z`, đính kèm **cả** `release\BestsellerCrawlerSetup-<version>.exe`
   và `release\BestsellerCrawler-<version>.zip` (bản 0.2.x chỉ biết tự cập nhật bằng zip).

## Build
```
build.bat              icon + test + PyInstaller one-folder + release\BestsellerCrawler-<version>.zip
build_installer.bat    build.bat rồi đóng gói thêm release\BestsellerCrawlerSetup-<version>.exe
```
Bộ cài lấy số phiên bản từ [app/app_version.py](app/app_version.py), script Inno Setup ở
[installer/BestsellerCrawler.iss](installer/BestsellerCrawler.iss).
