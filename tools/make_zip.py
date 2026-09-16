"""Zip dist\\BestsellerCrawler into release\\BestsellerCrawler-<version>.zip and verify the result."""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.app_version import APP_VERSION  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "dist" / "BestsellerCrawler"
TARGET = ROOT / "release" / f"BestsellerCrawler-{APP_VERSION}.zip"


def main() -> int:
    if not SOURCE.is_dir():
        print("Chưa có thư mục dist, chạy PyInstaller trước")
        return 1
    files = [p for p in SOURCE.rglob("*") if p.is_file()]
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if TARGET.exists():
        TARGET.unlink()
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in files:
            zf.write(path, path.relative_to(SOURCE).as_posix())

    with zipfile.ZipFile(TARGET) as zf:
        packed = len(zf.namelist())
        broken = zf.testzip()
    if broken or packed != len(files):
        print(f"LỖI: nén thiếu hoặc hỏng ({packed}/{len(files)} file, hỏng: {broken})")
        return 1
    print(f"Đã nén {packed} file -> {TARGET} ({TARGET.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
