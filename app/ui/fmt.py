from datetime import datetime


def local_time(iso: str | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Stored timestamps are UTC ISO strings; show them in the machine's timezone."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone().strftime(fmt)
    except ValueError:
        return iso
