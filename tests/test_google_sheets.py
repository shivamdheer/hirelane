from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from hirelane.db import DB
from hirelane.google import sheets
from hirelane.models import STATUS_APPROVED, STATUS_READY, STATUS_SUBMITTED, Posting

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


class _Exec:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def execute(self) -> dict[str, Any]:
        return self.value


class FakeSheets:
    """Records writes and serves the rows the test sets up."""

    def __init__(self, existing: list[list[str]] | None = None) -> None:
        self.existing = existing or []
        self.updates: list[tuple[str, list[list[str]]]] = []
        self.cleared: list[str] = []
        self.created = 0

    def spreadsheets(self) -> FakeSheets:
        return self

    def values(self) -> FakeSheets:
        return self

    def create(self, body: dict[str, Any], fields: str) -> _Exec:
        self.created += 1
        return _Exec({"spreadsheetId": "sheet-1"})

    def get(self, spreadsheetId: str, range: str) -> _Exec:
        return _Exec({"values": self.existing})

    def update(self, spreadsheetId: str, range: str, valueInputOption: str, body: dict[str, Any]) -> _Exec:
        self.updates.append((range, body["values"]))
        return _Exec({})

    def clear(self, spreadsheetId: str, range: str, body: dict[str, Any]) -> _Exec:
        self.cleared.append(range)
        return _Exec({})


@pytest.fixture
def db(tmp_path: Path):
    with DB(tmp_path / "t.db") as d:
        for i, (company, status) in enumerate([("Fabrikam", STATUS_READY), ("Contoso", STATUS_SUBMITTED)]):
            p = Posting(ats="greenhouse", slug=company.lower(), job_id=str(i), company=company, title="Data Analyst",
                        location="Remote, US")
            d.add_posting(p, status=status, fit="A", now=datetime(2026, 3, 9 + i, tzinfo=UTC))
        yield d


def test_sync_pushes_a_header_and_one_row_per_job(db: DB) -> None:
    fake = FakeSheets()
    result = sheets.sync(fake, db, "sheet-1", NOW)
    assert result.pushed == 2 and result.decisions == []
    rng, values = fake.updates[0]
    assert rng == "A1" and values[0][:3] == ["Key", "Company", "Role"] and len(values[0]) == 11
    assert [r[1] for r in values[1:]] == ["Contoso", "Fabrikam"]


def test_decisions_in_column_l_are_applied_then_marked_done(db: DB) -> None:
    key = "greenhouse:fabrikam:0"
    existing = [[key, "Fabrikam", "Data Analyst", "Resume ready", "A", "", "", "", "", "", "", "approve"],
                ["greenhouse:contoso:1", "Contoso", "Data Analyst", "Submitted", "A", "", "", "", "", "", "", "skip"]]
    fake = FakeSheets(existing)
    result = sheets.sync(fake, db, "sheet-1", NOW)
    assert db.get_job(key).status == STATUS_APPROVED  # type: ignore[union-attr]
    assert db.get_job("greenhouse:contoso:1").status == STATUS_SUBMITTED  # type: ignore[union-attr]
    assert len(result.decisions) == 1 and "not possible" in result.errors[0]
    marks = {rng: v[0][0] for rng, v in fake.updates if rng.startswith("L")}
    assert marks["L2"] == "done: approve" and marks["L3"].startswith("done: skip is not possible")


def test_done_unknown_and_empty_decisions(db: DB) -> None:
    existing = [["greenhouse:fabrikam:0", "", "", "", "", "", "", "", "", "", "", "done: approve"],
                ["greenhouse:contoso:1", "", "", "", "", "", "", "", "", "", ""],
                ["greenhouse:contoso:1", "", "", "", "", "", "", "", "", "", "", "maybe"]]
    result = sheets.sync(FakeSheets(existing), db, "s", NOW)
    assert result.decisions == [] and result.errors == ["row 4: unknown decision 'maybe'"]
    assert db.get_job("greenhouse:fabrikam:0").status == STATUS_READY  # type: ignore[union-attr]


def test_rows_that_no_longer_exist_are_cleared(db: DB) -> None:
    existing = [["k"] + [""] * 10 for _ in range(5)]
    fake = FakeSheets(existing)
    sheets.sync(fake, db, "s", NOW)
    assert fake.cleared == ["A4:K6"]


def test_the_spreadsheet_is_created_once(db: DB) -> None:
    fake = FakeSheets()
    assert sheets.sheet_id_for(fake, db) == "sheet-1"
    assert sheets.sheet_id_for(fake, db) == "sheet-1"
    assert fake.created == 1
