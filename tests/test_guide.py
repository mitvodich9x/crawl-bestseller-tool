import re

from app.paths import guide_dir


def test_guide_images_exist():
    """Mọi ảnh trong guide.html phải có file thật (ảnh thiếu thì trang Hướng dẫn hiện ô trống)."""
    html = (guide_dir() / "guide.html").read_text(encoding="utf-8")
    images = re.findall(r'<img\s+src="([^"]+)"', html)
    assert len(images) >= 10
    missing = [name for name in images if not (guide_dir() / name).is_file()]
    assert missing == []


def test_guide_anchors_resolve():
    html = (guide_dir() / "guide.html").read_text(encoding="utf-8")
    targets = set(re.findall(r'<a name="([^"]+)"', html))
    links = set(re.findall(r'<a href="#([^"]+)"', html))
    assert links <= targets
