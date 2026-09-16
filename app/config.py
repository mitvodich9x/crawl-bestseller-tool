"""JSON settings: DEFAULTS deep-merged with data/settings.json, saved atomically."""
import copy
import json
import logging
import os
from datetime import date
from pathlib import Path

from app.paths import data_file

log = logging.getLogger(__name__)

DEFAULTS = {
    "search": {
        "site": "EBAY_US",
        # bestmatch/listdate -> standard quota, watchcount -> most-watched quota, bestselling -> monthly quota
        "sort_by": "bestmatch",
        "listing_type": "fixedprice",
        "max_pages": 10,
        # stop a keyword early after this many pages in a row without any sold item
        "stop_after_empty_pages": 3,
        "delay_min": 3.0,
        "delay_max": 7.0,
        "headless": True,
        # searches to leave unused in the daily quota
        "reserve_quota": 0,
    },
    # rules applied when a scan decides which items count as "kept"
    "scan_filters": [
        {"field": "start_age_days", "op": "<=", "value": 7},
        {"field": "total_sold", "op": ">=", "value": None},
        {"field": "days_per_sale", "op": "<=", "value": 7},
        {"field": "watchers", "op": ">=", "value": None},
        {"field": "price", "op": "<=", "value": None},
    ],
    "schedule": {
        "mode": "every_n_days",  # manual | every_n_days | odd_days | even_days
        "n_days": 2,
        "anchor_date": None,  # ISO date, filled on first load
        "time": "08:00",
    },
    "state": {
        "last_run_date": None,
    },
    "general": {
        "minimize_to_tray": True,
        "autostart": False,
    },
}

SETTINGS_FILE = "settings.json"


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _path() -> Path:
    return data_file(SETTINGS_FILE)


def load() -> dict:
    stored = {}
    path = _path()
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Cannot read %s, using defaults: %s", path, exc)
    cfg = _deep_merge(DEFAULTS, stored)
    if not cfg["schedule"].get("anchor_date"):
        cfg["schedule"]["anchor_date"] = date.today().isoformat()
    return cfg


def save(cfg: dict) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
