"""Calendar: propose a few free slots for a scheduling reply. Read-only, it never creates an event."""
from __future__ import annotations

from datetime import datetime, time, timedelta, tzinfo
from typing import Any

SLOT_MINUTES = 30
DAY_START = time(9, 0)
DAY_END = time(17, 0)
DEFAULT_COUNT = 4
DEFAULT_DAYS = 10
STEP_MINUTES = 30
FIRST_WEEKEND_DAY = 5          # datetime.weekday(): Saturday

Interval = tuple[datetime, datetime]


def free_slots(busy: list[Interval], now: datetime, tz: tzinfo, count: int = DEFAULT_COUNT,
               days: int = DEFAULT_DAYS, slot_minutes: int = SLOT_MINUTES) -> list[Interval]:
    """Up to ``count`` free slots on weekdays between 9 and 17, at most one per day, starting tomorrow."""
    local_now = now.astimezone(tz)
    spans = sorted((s.astimezone(tz), e.astimezone(tz)) for s, e in busy)
    out: list[Interval] = []
    day = (local_now + timedelta(days=1)).date()
    for _ in range(days * 2):
        if len(out) >= count or (day - local_now.date()).days > days:
            break
        if day.weekday() < FIRST_WEEKEND_DAY:
            cursor = datetime.combine(day, DAY_START, tzinfo=tz)
            end_of_day = datetime.combine(day, DAY_END, tzinfo=tz)
            while cursor + timedelta(minutes=slot_minutes) <= end_of_day:
                slot = (cursor, cursor + timedelta(minutes=slot_minutes))
                if not any(s < slot[1] and e > slot[0] for s, e in spans):
                    out.append(slot)
                    break
                cursor += timedelta(minutes=STEP_MINUTES)
        day += timedelta(days=1)
    return out


def fetch_busy(svc: Any, start: datetime, end: datetime) -> list[Interval]:
    body = {"timeMin": start.isoformat(), "timeMax": end.isoformat(), "items": [{"id": "primary"}]}
    reply = svc.freebusy().query(body=body).execute()
    spans = reply.get("calendars", {}).get("primary", {}).get("busy", [])
    return [(datetime.fromisoformat(b["start"].replace("Z", "+00:00")),
             datetime.fromisoformat(b["end"].replace("Z", "+00:00"))) for b in spans]


def _clock(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def describe(slots: list[Interval]) -> list[str]:
    """Plain lines such as 'Monday March 9, 9:00 AM to 9:30 AM CDT'."""
    return [f"{s:%A %B} {s.day}, {_clock(s)} to {_clock(e)} {e:%Z}" for s, e in slots]
