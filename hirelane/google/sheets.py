"""Google Sheets tracking. The database stays the source of truth and the sheet is a readable mirror.

Columns A to K are written by hirelane. Column L, Decision, belongs to the user: type approve or skip next to a job
and the next sync applies it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..actions import ActionError, apply_action
from ..db import DB

SHEET_TITLE = "hirelane"
META_SHEET_ID = "google_sheet_id"
HEADERS = ["Key", "Company", "Role", "Status", "Fit", "Track", "Location", "Pay", "Posted", "Applied", "Note",
           "Decision"]
MIRROR_COLUMNS = len(HEADERS) - 1
DECISION_COL = "L"
DECISIONS = {"approve": "approve", "approved": "approve", "skip": "skip", "retry": "retry"}


@dataclass
class SyncResult:
    pushed: int = 0
    decisions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def create_spreadsheet(svc: Any) -> str:
    body = {"properties": {"title": SHEET_TITLE}}
    return str(svc.spreadsheets().create(body=body, fields="spreadsheetId").execute()["spreadsheetId"])


def rows_for(db: DB) -> list[list[str]]:
    rows = []
    for j in db.jobs(order="added_at DESC"):
        rows.append([j.key, j.company, j.role, j.status, j.fit, j.track, j.location, j.pay, j.posted,
                     j.submitted_at[:10], j.needs_reason[:200]])
    return rows


def sync(svc: Any, db: DB, sheet_id: str, now: datetime) -> SyncResult:
    """Apply the user's decisions from the sheet, then write the current state back."""
    result = SyncResult()
    values = svc.spreadsheets().values()
    existing = values.get(spreadsheetId=sheet_id, range=f"A2:{DECISION_COL}").execute().get("values", [])
    cleared: list[tuple[int, str]] = []
    for i, row in enumerate(existing, start=2):
        decision = (row[MIRROR_COLUMNS].strip().lower() if len(row) > MIRROR_COLUMNS else "")
        if not decision or decision.startswith("done"):
            continue
        action = DECISIONS.get(decision)
        if action is None:
            result.errors.append(f"row {i}: unknown decision {decision!r}")
            continue
        try:
            msg = apply_action(db, row[0], action, now)
            result.decisions.append(msg)
            cleared.append((i, f"done: {action}"))
        except ActionError as e:
            result.errors.append(f"row {i}: {e}")
            cleared.append((i, f"done: {e}"[:60]))
    rows = rows_for(db)
    values.update(spreadsheetId=sheet_id, range="A1", valueInputOption="RAW",
                  body={"values": [HEADERS[:MIRROR_COLUMNS], *rows]}).execute()
    stale = len(existing) - len(rows)
    if stale > 0:
        values.clear(spreadsheetId=sheet_id, range=f"A{len(rows) + 2}:K{len(existing) + 1}", body={}).execute()
    for row_number, note in cleared:
        values.update(spreadsheetId=sheet_id, range=f"{DECISION_COL}{row_number}", valueInputOption="RAW",
                      body={"values": [[note]]}).execute()
    result.pushed = len(rows)
    return result


def sheet_id_for(svc: Any, db: DB) -> str:
    """The stored spreadsheet id, creating the spreadsheet on first use."""
    sid = db.get_meta(META_SHEET_ID)
    if not sid:
        sid = create_spreadsheet(svc)
        db.set_meta(META_SHEET_ID, sid)
    return sid
