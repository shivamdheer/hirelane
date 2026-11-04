from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from hirelane.google import calendar

TZ = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")
FRIDAY = datetime(2026, 3, 6, 15, 0, tzinfo=TZ)           # a Friday afternoon


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=TZ)


def test_slots_skip_weekends_and_start_after_today() -> None:
    slots = calendar.free_slots([], FRIDAY, TZ, count=3)
    assert [s.strftime("%a %d %H:%M") for s, _ in slots] == ["Mon 09 09:00", "Tue 10 09:00", "Wed 11 09:00"]
    assert all(e - s == timedelta(minutes=30) for s, e in slots)


def test_busy_time_moves_the_slot_within_the_day() -> None:
    busy = [(at(9, 9), at(9, 11, 15))]
    (first, *_rest) = calendar.free_slots(busy, FRIDAY, TZ, count=2)
    assert first[0] == at(9, 11, 30)


def test_a_fully_booked_day_is_skipped() -> None:
    busy = [(at(9, 8), at(9, 18))]
    slots = calendar.free_slots(busy, FRIDAY, TZ, count=2)
    assert slots[0][0].day == 10


def test_busy_times_in_utc_are_compared_in_the_users_zone() -> None:
    start = at(9, 9).astimezone(UTC)
    busy = [(start, start + timedelta(hours=8))]
    assert calendar.free_slots(busy, FRIDAY, TZ, count=1)[0][0].day == 10


def test_nothing_is_proposed_beyond_the_window() -> None:
    busy = [(at(d, 0), at(d, 23)) for d in range(7, 31)]
    assert calendar.free_slots(busy, FRIDAY, TZ, count=3, days=5) == []


class FakeCalendar:
    def freebusy(self) -> FakeCalendar:
        return self

    def query(self, body: dict[str, Any]) -> FakeCalendar:
        self.body = body
        return self

    def execute(self) -> dict[str, Any]:
        return {"calendars": {"primary": {"busy": [{"start": "2026-03-09T15:00:00Z", "end": "2026-03-09T16:00:00Z"}]}}}


def test_fetch_busy_parses_utc_intervals() -> None:
    svc = FakeCalendar()
    (span,) = calendar.fetch_busy(svc, FRIDAY, FRIDAY + timedelta(days=10))
    assert span[0].isoformat() == "2026-03-09T15:00:00+00:00"
    assert svc.body["items"] == [{"id": "primary"}]


def test_describe_is_plain_text() -> None:
    (line,) = calendar.describe(calendar.free_slots([], FRIDAY, TZ, count=1))
    assert line.startswith("Monday March 9, 9:00 AM to 9:30 AM CDT")
