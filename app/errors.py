"""Đổi lỗi kỹ thuật thành câu người dùng hiểu được."""
from app import browser_setup


def friendly_error(exc: Exception | str) -> str:
    text = str(exc)
    lowered = text.lower()
    if "executable doesn't exist" in lowered or "chromium" in lowered and "không tải được" in lowered:
        return ("Chưa tải được trình duyệt Chromium. Kiểm tra kết nối mạng rồi bấm lại; "
                f"app tải về thư mục {browser_setup.browsers_dir()}")
    if "timeout" in lowered:
        return "Quá thời gian chờ mạng. Kiểm tra kết nối rồi thử lại."
    stripped = text.strip()
    return stripped.splitlines()[0][:300] if stripped else repr(exc)
