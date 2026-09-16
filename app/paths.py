"""Filesystem locations that work both from source and from a PyInstaller build."""
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    path = app_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_file(name: str) -> Path:
    return data_dir() / name


def browser_profile_dir() -> Path:
    path = data_dir() / "browser_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def image_cache_dir() -> Path:
    path = data_dir() / "image_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
