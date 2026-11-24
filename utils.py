from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config


def today_str() -> str:
    return datetime.now(ZoneInfo(config.DAY_TZ)).strftime("%Y-%m-%d")


def until_reset() -> str:
    now = datetime.now(ZoneInfo(config.DAY_TZ))
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    secs = int((nxt - now).total_seconds())
    h, m = divmod(secs // 60, 60)
    return f"{h}h {m}m"


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def clean_uid(raw: str):
    s = "".join(c for c in str(raw).strip() if c.isdigit())
    return s if 5 <= len(s) <= 12 else None
