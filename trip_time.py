"""Trip date/time handling in Indian Standard Time (no DST, no tzdata needed)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple

IST = timezone(timedelta(hours=5, minutes=30))
MAX_ADVANCE_DAYS = 7  # weather forecasts are only reliable for about a week


def now_ist() -> datetime:
    """Current India time as a naive datetime (so it compares with picker values)."""
    return datetime.now(IST).replace(tzinfo=None)


def default_schedule(now: Optional[datetime] = None) -> Tuple[date, time]:
    """Suggested advance-booking slot: one hour from now, rounded up to a quarter hour."""
    now = now or now_ist()
    later = (now + timedelta(hours=1)).replace(second=0, microsecond=0)
    later += timedelta(minutes=(-later.minute) % 15)
    return later.date(), later.time()


def resolve_trip_datetime(mode: str, sched_date: Optional[date], sched_time: Optional[time],
                          now: Optional[datetime] = None) -> Tuple[datetime, Optional[str]]:
    """Return (trip_datetime, message).

    mode "now"       -> current time.
    mode "scheduled" -> the chosen date+time; if it is in the past or too far ahead we fall back to
                        'now' and return a message explaining why.
    """
    now = now or now_ist()
    if mode != "scheduled":
        return now, None
    if sched_date is None or sched_time is None:
        return now, "Pick a date and time - using the current time for now."
    chosen = datetime.combine(sched_date, sched_time)
    if chosen < now.replace(second=0, microsecond=0):
        return now, "That time has already passed - using the current time instead."
    if chosen > now + timedelta(days=MAX_ADVANCE_DAYS):
        return now, f"Bookings can be planned up to {MAX_ADVANCE_DAYS} days ahead - using the current time instead."
    return chosen, None


def format_trip_time(dt: datetime) -> str:
    return f"{dt:%a %d %b, %I:%M %p} IST"
