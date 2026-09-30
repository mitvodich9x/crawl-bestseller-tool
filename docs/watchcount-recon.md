# Khảo sát watchcount.com (2026-09-15)

## Tổng quan
- `www.watchcount.com` (bản cũ): request thường bị **403**; mở bằng trình duyệt thật thì vào được nhưng tìm kiếm qua URL `?q=` không ra kết quả (bị reCAPTCHA chặn). **Không dùng bản này.**
- `beta.watchcount.com` (bản mới): mở bằng Playwright headful được (HTTP 200), có reCAPTCHA v3 chạy ngầm (`/recaptcha_verify`), không có challenge chặn cứng.

## URL tìm kiếm
```
https://beta.watchcount.com/{status}/{keywords}/{category}/{listingType}?{params}
```
- `status`: `live` | `sold`
- `keywords`: encodeURIComponent, dấu cách thành `+`; `-` nếu không có từ khoá
- `category`: `-` hoặc `{slug}_{id}` (vd `clothing-shoes-accessories_11450`)
- `listingType`: `all` | `auction` | `fixedprice` | `bestoffer`
- Query params (xếp theo alphabet, bỏ giá trị null/rỗng/0): `site=EBAY_US`, `sortBy`, `sortOrder`, `offset`, `startTimeFrom`, `startTimeTo`, `lastSoldDate`, `minPrice`, `maxPrice`, `condition`, `seller`, `excludeSellers`, `exactKeywordMatch`, `freeShippingOnly`, `itemLocation`...

Ví dụ Best Selling, listing mới trong 7 ngày:
```
https://beta.watchcount.com/live/funny+shirt/-/fixedprice?site=EBAY_US&sortBy=bestselling&startTimeFrom=7days
```

### Giá trị lọc có sẵn
- `sortBy`: `bestselling` (**chỉ dùng với listingType=fixedprice**), `watchcount`, `bids`, `bestmatch`, `price`, `listdate`, `enddate` (+ `sortOrder` asc/desc)
- `startTimeFrom` (listing đăng trong vòng): `1hour`…`12hours`, `1day`…`7days`, `14days`, `30days`, `60days`, `90days`, `180days`, `1year`…`10years`
- `lastSoldDate` (bán gần nhất trong vòng): `1day`, `2days`, `3days`, `7days`, `14days`, `30days`, `45days`, `60days`

→ Bộ lọc "start > 7 ngày thì loại" làm được **ngay trên server** bằng `startTimeFrom=7days`.

## Phân trang
- 20 item/trang, `offset=20, 40, ...`
- JSON có sẵn `nextLink`, `nextOffset`, `total`.

## Dữ liệu: JSON nhúng sẵn trong HTML (không cần parse DOM)
Trang kết quả có sẵn `window.searchRequest = {...}` và `window.searchResult = {...}`, lấy bằng `page.evaluate("() => window.searchResult")`.

`searchResult` gồm: `items[]`, `total`, `limit`, `nextOffset`, `nextLink`, `error`, `categoryHistogram`, `dominantCategoryName`, `shareStats`.

Các trường của mỗi item dùng cho tool:

| Trường | Ví dụ | Dùng cho |
|---|---|---|
| `id` | `297239851044` | khoá chính |
| `title` | Mens Funny T Shirts ... | cột Tiêu đề |
| `image` | `https://i.ebayimg.com/images/g/.../s-l225.jpg` | cột Hình ảnh (đổi `s-l225` thành `s-l1600` để lấy ảnh lớn) |
| `quantitySold` | 1484 | tổng đơn |
| `oneUnitEvery` | `2.9 sold/day`, `1.0 sold/week`, `1.7 sold/month`, `4.3 sold/year`, null | **tốc độ bán trung bình (sell one)** |
| `quantitySoldRate` | `87.1 sold per month`, `2.7 months to sell one` | tốc độ bán (dạng khác) |
| `startTime` / `startTimeFormatted` | `2025-04-22T03:09:48Z` / `22-Apr-25` | start date |
| `timeRunning` | 511.0 (ngày) | số ngày đã chạy |
| `watchCount` | 1075 | số người theo dõi |
| `price`, `priceFormatted`, `shipping`, `currency` | `$5.00 to $9.50` | giá |
| `quantityAvailable`, `hasVariations`, `condition`, `listingType` | | thông số phụ |
| `seller`, `sellerFeedbackScore`, `sellerFeedbackPercentage` | | người bán |
| `primaryCategory`, `primaryCategoryTree` | | danh mục |
| `estimatedTotalSalesFormatted` | `$7,420 to $14,098` | doanh thu ước tính |
| `itemRedirectURL`, `historyRedirectURL` | rb.watchcount.com/go?... | link eBay / lịch sử mua |

Link eBay trực tiếp dựng từ id: `https://www.ebay.com/itm/{id}`.

Watchcount **không** trả số lượng bán theo từng ngày. "Sold trong 7/3/1 ngày gần nhất" chỉ lấy được bằng cách mở trang `ebay.com/bin/purchaseHistory/{id}` của từng item: chậm, dễ bị eBay chặn, và lịch sử chỉ có ngày giờ + số lượng.

## Giới hạn & tài khoản (quan trọng)
`GET /guest/usage` khi chưa đăng nhập:
```json
{"max_daily_searches":20,"max_most_watched":20,"max_standard":20,
 "max_best_selling":1,"best_selling_remaining":1}
```
- Khách (guest): **20 lượt/ngày**, Best Selling chỉ **1 lượt**.
- `MIN_PLAN_NAME = "Free"`: Best Selling mở khoá khi **đăng nhập tài khoản Free**. Hạn mức của tài khoản Free/Starter chưa rõ, phải đăng nhập mới kiểm tra được (trang `/subscription`).
- Mỗi trang (mỗi offset) có thể tính là 1 lượt, nên số từ khoá × số trang bị giới hạn bởi hạn mức gói.

## Hạn mức thực tế (đo bằng tài khoản Free, `GET /user/usage`)
| Gói | Giá (beta) | Lượt/ngày (search) | Best Selling/tháng |
|---|---|---|---|
| Free | 0 | 50 most-watched, 200 standard | **3** |
| Starter | $19 | 100 | 15 |
| Pro | $39 | 150 | 50 |
| Business | $89 | 200 | 150 |
| Advanced | $199 | 500 | 400 |

Hạn mức reset theo ngày tạo tài khoản (`resets_at`). Kiểm tra ngày 2026-09-15 cho thấy:
- **Mỗi trang (mỗi offset) tính là 1 lượt.** Sort Watch Count trừ vào `most_watched_count`; Best Match và Newly Listed trừ vào `standard_count`; `sortBy=bestselling` trừ vào `best_selling_count`.
- Đăng nhập thành công thì trang có `IS_LOGGED_IN = true` và `HAS_BEST_SELLING = true`.
- `lastSoldDate=3days` **không có tác dụng** với tìm kiếm live: total gần như không đổi, phần lớn item vẫn có sold = 0.
- Cùng từ khoá "funny shirt", fixedprice, startTimeFrom=7days, trang đầu:
  - Watch Count: 1/20 item có đơn
  - Newly Listed: 0/20
  - **Best Match: 5/20 item có đơn**, trong đó có các item bán 5.0/day và 3.1/day giống top Best Selling.
- `startTimeFrom` thỉnh thoảng trả về listing cũ hơn (vd 05-Aug-26), nên tool vẫn phải lọc lại start date.

## Trang xác minh /challenge (cập nhật 2026-09-28)
Từ khoảng 09/2026 mọi URL của `beta.watchcount.com` chuyển hướng sang `www.watchcount.com` (cùng giao diện,
cùng `window.searchResult`, `/user/usage`, `/guest/usage`). Cookie đăng nhập cũ gắn với host beta nên mất hiệu lực.

Trang `https://www.watchcount.com/challenge?returnURL=...&hadToken=false` là **reCAPTCHA**, không liên quan
đăng nhập (khách vẫn quét được sau khi qua):
1. Script trang gọi reCAPTCHA v3 rồi `POST /recaptcha_verify`; thành công thì `location.replace(returnURL)`.
2. Trượt v3 (`{"success":false,"error":"reCAPTCHA v3 verification failed"}`, luôn gặp với headless shell và
   profile mới) thì hiện ô reCAPTCHA v2, người dùng tích xong gọi `POST /challenge_verify` rồi quay lại returnURL.
3. Qua rồi thì được ghi vào phiên (`wc_frontend_session`), các lần sau kể cả chạy ẩn không bị hỏi lại.

Tool: gặp challenge thì chờ v3 tự qua (25s ẩn); không qua thì mở cửa sổ hiện, chờ người dùng tích (5 phút),
rồi quét tiếp. Đăng nhập chỉ bắt buộc với Best Selling; khách có 20 lượt standard/ngày, 1 lượt best selling.

## Thư mục trình duyệt của Playwright
Playwright chọn thư mục theo biến môi trường `PLAYWRIGHT_BROWSERS_PATH`
(xem `driver/package/lib/server/registry/index.js`):
- `0` → tìm trong `<gói playwright>/driver/package/.local-browsers` (bản đóng gói **không** có sẵn ở đây)
- có giá trị → dùng đúng đường dẫn đó
- để trống → `%LOCALAPPDATA%\ms-playwright`

Máy nào đã có sẵn biến này (do tool khác cài) sẽ làm app tìm sai chỗ và báo
"Executable doesn't exist at ...\.local-browsers\chromium-1208\chrome-win64\chrome.exe".
Vì vậy app luôn tự ấn định `PLAYWRIGHT_BROWSERS_PATH` về `%LOCALAPPDATA%\ms-playwright` lúc khởi động.

Cấu trúc thư mục thật (tên thư mục con khác nhau giữa hai loại):
```
ms-playwright\chromium-1228\chrome-win64\chrome.exe
ms-playwright\chromium_headless_shell-1228\chrome-headless-shell-win64\chrome-headless-shell.exe
```

## Kết luận cho thiết kế
1. Scraper dùng Playwright persistent profile trên `www.watchcount.com` (trước là beta). User đăng nhập 1 lần trong profile đó.
2. Lấy dữ liệu bằng `window.searchResult`, không cần selector DOM, nên không cần `extract_list.js`.
3. Lọc start date bằng `startTimeFrom` ngay trên URL; lọc tổng đơn và sell-one ở phía tool.
4. Đọc `/guest/usage` (hoặc endpoint usage của user) trước khi quét để báo lượt còn lại, dừng khi hết lượt.

## Tab Search Sold (khảo sát 2026-09-28)
- URL: `https://www.watchcount.com/sold/{keywords}/{category}/{listingType}?site=EBAY_US&sortBy=bestmatch&lastSoldDate=7days`
  (tab Live là `/live/...`). Dữ liệu vẫn ở `window.searchResult`, phân trang `offset`/`nextOffset` như Live.
- Sắp xếp: chỉ `bestmatch`, `price` + `sortOrder=asc|desc`. Watch Count / Newly Listed / Best Selling chỉ có ở Live.
- Lọc thêm `lastSoldDate`: `1day`, `2days`, `3days`, `7days`, `14days`, `30days`, `45days`, `60days`.
- `startTimeFrom` **không có tác dụng** ở tab Sold (kiểm tra 2026-09-30): `searchRequest` vẫn nhận giá trị nhưng
  total và danh sách item y hệt khi bỏ tham số (vd "glass suncatcher", lastSoldDate=7days: 512 cả hai), vẫn có listing
  đăng 300+ ngày. Tool chỉ gửi `startTimeFrom` với tab Live, còn tab Sold thì lọc Start trong tool.
- Mỗi trang tốn 1 lượt **standard** (giống Best Match).
- Item có thêm `lastSoldDate` (ISO), `lastSoldFor`, `lastSoldForFormatted`, `endTime`.
- Mỗi item là listing **đã bán hết**: `status` = "Sold", `quantityAvailable` = 0, `quantitySold` luôn = 1 (đo 2026-09-30
  trên 200 item của "glass suncatcher" và "Eileen Fisher"). `oneUnitEvery` / `quantitySoldRate` = 1 đơn / `timeRunning`,
  nên Tổng đơn và Sell one không phản ánh độ bán chạy. Tool bỏ qua ba điều kiện Tổng đơn, Sell one, Số đơn TB/ngày
  khi quét tab Sold.
- Con số watchcount hiện trên web với Last sold = 1 ngày: "glass suncatcher" 82, "Eileen Fisher" 378 (2026-09-30).
- Mỗi lần mở trang, reCAPTCHA v3 chạy ngầm (`/recaptcha_verify`); profile đã qua xác minh thì không bị chặn.
