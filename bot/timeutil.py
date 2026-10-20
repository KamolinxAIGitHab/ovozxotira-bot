"""Тошкент вақти (UTC+5) билан ишлаш. Базада вақт UTC да сақланади."""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

UZ_TZ = timezone(timedelta(hours=5))  # Ўзбекистонда ёзги вақтга ўтиш йўқ


def now_local() -> datetime:
    return datetime.now(UZ_TZ)


def today_local() -> date:
    return now_local().date()


def reply_time() -> str:
    return now_local().strftime("%H:%M:%S")


def to_local(value) -> Optional[datetime]:
    """Базадан келган UTC вақтни Тошкент вақтига ўгиради."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(UZ_TZ)


def fmt_time(value) -> str:
    dt = to_local(value)
    return dt.strftime("%H:%M") if dt else ""


def fmt_date(value) -> str:
    dt = to_local(value)
    return dt.strftime("%d.%m.%Y") if dt else ""


def day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Тошкент вақти бўйича кун бошланиши ва охири (базадаги UTC қиймат шаклида)."""
    start_local = datetime(day.year, day.month, day.day, tzinfo=UZ_TZ)
    start = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start, start + timedelta(days=1)


def format_elapsed(seconds: float) -> str:
    """Масалан: 4,2 сония; 1 дақиқа 5 сония."""
    if seconds < 60:
        return f"{seconds:.1f}".replace(".", ",") + " сония"
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes} дақиқа {secs} сония"


def is_stale(value, minutes: int = 10) -> bool:
    dt = to_local(value)
    return bool(dt) and now_local() - dt > timedelta(minutes=minutes)
