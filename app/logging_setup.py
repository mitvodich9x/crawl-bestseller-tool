import logging
import sys
from logging.handlers import RotatingFileHandler

from app.paths import logs_dir


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(logs_dir() / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    if sys.stdout is not None:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        root.addHandler(console)
