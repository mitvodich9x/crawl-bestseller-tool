"""Pure schedule math: which days a scan is due and when the next one is."""
from datetime import date, datetime, time, timedelta

MODES = {
    "manual": "Thủ công (chỉ khi bấm Quét ngay)",
    "every_n_days": "Mỗi N ngày một lần",
    "odd_days": "Các ngày lẻ (1, 3, 5...)",
    "even_days": "Các ngày chẵn (2, 4, 6...)",
}


def parse_time(value: str) -> time:
    hour, minute = (int(x) for x in (value or "08:00").split(":")[:2])
    return time(hour, minute)


def is_scan_day(day: date, schedule: dict) -> bool:
    mode = schedule.get("mode", "manual")
    if mode == "every_n_days":
        n = max(1, int(schedule.get("n_days") or 1))
        anchor = date.fromisoformat(schedule.get("anchor_date") or day.isoformat())
        return (day - anchor).days % n == 0
    if mode == "odd_days":
        return day.day % 2 == 1
    if mode == "even_days":
        return day.day % 2 == 0
    return False


def should_run(now: datetime, schedule: dict, last_run_date: str | None) -> bool:
    """Due when today is a scan day, the scan time has passed, and today hasn't run yet.

    Because it only checks "time has passed", starting the app late on a scan day catches up once.
    """
    if schedule.get("mode", "manual") == "manual":
        return False
    today = now.date()
    if last_run_date == today.isoformat():
        return False
    if not is_scan_day(today, schedule):
        return False
    return now.time() >= parse_time(schedule.get("time", "08:00"))


def next_run(now: datetime, schedule: dict, last_run_date: str | None, horizon_days: int = 400) -> datetime | None:
    if schedule.get("mode", "manual") == "manual":
        return None
    run_at = parse_time(schedule.get("time", "08:00"))
    for offset in range(horizon_days):
        day = now.date() + timedelta(days=offset)
        if not is_scan_day(day, schedule):
            continue
        if day == now.date():
            if last_run_date == day.isoformat():
                continue
            # today's slot already passed but not run -> it will fire right away
            return max(datetime.combine(day, run_at), now.replace(second=0, microsecond=0))
        return datetime.combine(day, run_at)
    return None
