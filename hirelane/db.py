"""SQLite state. The database is the source of truth and every job is addressed by its key."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import get_paths
from .models import APPLIED_STATUSES, Job, Posting
from .textutil import file_key, norm_company, norm_title

LOCK_MINUTES = 30
BUSY_TIMEOUT_MS = 10_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  key TEXT PRIMARY KEY,
  company TEXT NOT NULL,
  role TEXT NOT NULL,
  status TEXT NOT NULL,
  track TEXT DEFAULT '',
  location TEXT DEFAULT '',
  pay TEXT DEFAULT '',
  posted TEXT DEFAULT '',
  fit TEXT DEFAULT '',
  score REAL DEFAULT 0,
  ats TEXT DEFAULT '',
  ats_slug TEXT DEFAULT '',
  ats_job_id TEXT DEFAULT '',
  apply_url TEXT DEFAULT '',
  desc_text TEXT DEFAULT '',
  file_key TEXT DEFAULT '',
  resume_file TEXT DEFAULT '',
  gaps TEXT DEFAULT '[]',
  notes TEXT DEFAULT '',
  needs_reason TEXT DEFAULT '',
  added_at TEXT DEFAULT '',
  decided_at TEXT DEFAULT '',
  submitted_at TEXT DEFAULT '',
  attempts INTEGER DEFAULT 0,
  lock_until TEXT DEFAULT '',
  title_norm TEXT DEFAULT '',
  company_norm TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_company_title ON jobs(company_norm, title_norm);

CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_key TEXT NOT NULL,
  at TEXT NOT NULL,
  phase TEXT NOT NULL,
  detail TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS attempts_job ON attempts(job_key);

CREATE TABLE IF NOT EXISTS seen (
  ats TEXT NOT NULL,
  ats_job_id TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  PRIMARY KEY (ats, ats_job_id)
);

CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_key TEXT NOT NULL,
  label TEXT NOT NULL,
  label_norm TEXT NOT NULL,
  options TEXT DEFAULT '[]',
  answer TEXT DEFAULT '',
  status TEXT DEFAULT 'open',
  created_at TEXT DEFAULT '',
  UNIQUE(job_key, label_norm)
);

CREATE TABLE IF NOT EXISTS proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_key TEXT DEFAULT '',
  experience TEXT NOT NULL,
  kind TEXT NOT NULL,
  target TEXT DEFAULT '',
  text TEXT NOT NULL,
  reason TEXT DEFAULT '',
  status TEXT DEFAULT 'pending',
  created_at TEXT DEFAULT '',
  decided_at TEXT DEFAULT '',
  UNIQUE(experience, kind, target, text)
);

CREATE TABLE IF NOT EXISTS resumes (
  job_key TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  ok INTEGER NOT NULL,
  problems TEXT DEFAULT '[]',
  warnings TEXT DEFAULT '[]',
  coverage INTEGER DEFAULT 0,
  record TEXT DEFAULT '',
  created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS emails (
  thread_id TEXT PRIMARY KEY,
  received TEXT DEFAULT '',
  from_addr TEXT DEFAULT '',
  subject TEXT DEFAULT '',
  kind TEXT DEFAULT '',
  company TEXT DEFAULT '',
  job_key TEXT DEFAULT '',
  summary TEXT DEFAULT '',
  handled_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task TEXT NOT NULL,
  started TEXT NOT NULL,
  finished TEXT DEFAULT '',
  ok INTEGER DEFAULT 0,
  summary TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""

JOB_COLUMNS = {f.name for f in fields(Job)}


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


def job_key(posting: Posting) -> str:
    return f"{posting.ats}:{posting.slug}:{posting.job_id}"


class DB:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_paths().db
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One connection is shared by the web server's worker threads, and SQLite serializes the writes.
        self._conn = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> DB:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    # jobs

    def add_posting(self, posting: Posting, *, status: str, track: str = "", fit: str = "", score: float = 0.0,
                    now: datetime | None = None) -> Job:
        """Insert a posting as a job. An existing key is returned unchanged."""
        key = job_key(posting)
        existing = self.get_job(key)
        if existing:
            return existing
        job = Job(
            key=key, company=posting.company, role=posting.title, status=status, track=track, location=posting.location,
            pay=posting.pay, posted=posting.posted, fit=fit, score=score, ats=posting.ats, ats_slug=posting.slug,
            ats_job_id=posting.job_id, apply_url=posting.apply_url or posting.url, desc_text=posting.description,
            file_key=file_key(posting.company), added_at=iso(now or datetime.now().astimezone()),
            title_norm=norm_title(posting.title), company_norm=norm_company(posting.company),
        )
        cols = list(asdict(job))
        with self.tx() as c:
            c.execute(f"INSERT INTO jobs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                      [getattr(job, k) for k in cols])
        return job

    def get_job(self, key: str) -> Job | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
        return Job.from_row(row) if row else None

    def jobs(self, *statuses: str, order: str = "score DESC, added_at") -> list[Job]:
        sql = "SELECT * FROM jobs"
        args: tuple[str, ...] = ()
        if statuses:
            sql += f" WHERE status IN ({','.join('?' * len(statuses))})"
            args = statuses
        return [Job.from_row(r) for r in self._conn.execute(f"{sql} ORDER BY {order}", args)]

    def update_job(self, key: str, **changes: Any) -> None:
        unknown = set(changes) - JOB_COLUMNS
        if unknown:
            raise KeyError(f"unknown job columns: {sorted(unknown)}")
        if not changes:
            return
        sets = ", ".join(f"{k}=?" for k in changes)
        with self.tx() as c:
            c.execute(f"UPDATE jobs SET {sets} WHERE key=?", [*changes.values(), key])

    def status_counts(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT status, COUNT(*) n FROM jobs GROUP BY status")
        return {r["status"]: r["n"] for r in rows}

    def applied_companies(self) -> set[str]:
        marks = ",".join("?" * len(APPLIED_STATUSES))
        rows = self._conn.execute(f"SELECT company_norm FROM jobs WHERE status IN ({marks})", APPLIED_STATUSES)
        return {r["company_norm"] for r in rows}

    def find_duplicate(self, company: str, title: str) -> Job | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE company_norm=? AND title_norm=? LIMIT 1",
                                 (norm_company(company), norm_title(title))).fetchone()
        return Job.from_row(row) if row else None

    def submitted_today(self, day: str) -> int:
        row = self._conn.execute("SELECT COUNT(*) n FROM jobs WHERE submitted_at LIKE ?", (f"{day}%",)).fetchone()
        return int(row["n"])

    # one lock per job so nothing is filled or submitted twice at the same time

    def claim(self, key: str, now: datetime, from_statuses: tuple[str, ...]) -> bool:
        until = iso(now + timedelta(minutes=LOCK_MINUTES))
        marks = ",".join("?" * len(from_statuses))
        with self.tx() as c:
            cur = c.execute(
                f"UPDATE jobs SET lock_until=?, attempts=attempts+1 WHERE key=? AND status IN ({marks}) "
                "AND (lock_until='' OR lock_until<?)",
                [until, key, *from_statuses, iso(now)])
            return cur.rowcount == 1

    def release(self, key: str) -> None:
        self.update_job(key, lock_until="")

    # attempts and phases

    def add_attempt(self, key: str, phase: str, detail: str = "", now: datetime | None = None) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO attempts (job_key, at, phase, detail) VALUES (?,?,?,?)",
                      (key, iso(now or datetime.now().astimezone()), phase, detail[:500]))

    def attempt_phases(self, key: str) -> list[str]:
        rows = self._conn.execute("SELECT phase FROM attempts WHERE job_key=? ORDER BY id", (key,))
        return [r["phase"] for r in rows]

    # the stored resume record and the result of the ATS gate for it

    def save_resume(self, job_key: str, path: str, sha256: str, ok: bool, problems: list[str],
                    warnings: list[str], coverage: int, record: str, now: datetime | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO resumes (job_key, path, sha256, ok, problems, warnings, coverage, record, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(job_key) DO UPDATE SET path=excluded.path, "
                "sha256=excluded.sha256, ok=excluded.ok, problems=excluded.problems, warnings=excluded.warnings, "
                "coverage=excluded.coverage, record=excluded.record, created_at=excluded.created_at",
                (job_key, path, sha256, int(ok), json.dumps(problems), json.dumps(warnings), coverage, record,
                 iso(now or datetime.now().astimezone())))

    def get_resume(self, job_key: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM resumes WHERE job_key=?", (job_key,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["ok"] = bool(out["ok"])
        out["problems"] = json.loads(out["problems"] or "[]")
        out["warnings"] = json.loads(out["warnings"] or "[]")
        return out

    def count_attempts(self, day: str, phases: tuple[str, ...]) -> int:
        marks = ",".join("?" * len(phases))
        row = self._conn.execute(
            f"SELECT COUNT(*) n FROM attempts WHERE at LIKE ? AND phase IN ({marks})", (f"{day}%", *phases)).fetchone()
        return int(row["n"])

    # postings already seen on a board, so a job is only offered once

    def mark_seen(self, ats: str, job_id: str, now: datetime | None = None) -> bool:
        """True when this posting is new."""
        with self.tx() as c:
            cur = c.execute("INSERT OR IGNORE INTO seen (ats, ats_job_id, first_seen) VALUES (?,?,?)",
                            (ats, job_id, iso(now or datetime.now().astimezone())))
            return cur.rowcount == 1

    # runs

    def start_run(self, task: str, now: datetime | None = None) -> int:
        with self.tx() as c:
            cur = c.execute("INSERT INTO runs (task, started) VALUES (?,?)",
                            (task, iso(now or datetime.now().astimezone())))
            return int(cur.lastrowid or 0)

    def finish_run(self, run_id: int, ok: bool, summary: str, now: datetime | None = None) -> None:
        with self.tx() as c:
            c.execute("UPDATE runs SET finished=?, ok=?, summary=? WHERE id=?",
                      (iso(now or datetime.now().astimezone()), int(ok), summary[:1000], run_id))

    def last_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        return [dict(r) for r in self._conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]

    # questions the filler could not answer, shared by every job that asks them

    def add_question(self, job_key: str, label: str, options: list[str], now: datetime | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO questions (job_key, label, label_norm, options, created_at) VALUES (?,?,?,?,?)",
                (job_key, label[:500], norm_title(label), json.dumps(options[:50]),
                 iso(now or datetime.now().astimezone())))

    def open_questions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM questions WHERE status='open' ORDER BY id").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["options"] = json.loads(d["options"] or "[]")
            out.append(d)
        return out

    def answer_question(self, question_id: int, answer: str) -> dict[str, Any] | None:
        """Mark one question answered and every other open job that asked the same thing. Returns the question."""
        row = self._conn.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
        if row is None:
            return None
        with self.tx() as c:
            c.execute("UPDATE questions SET answer=?, status='answered' WHERE label_norm=? AND status='open'",
                      (answer, row["label_norm"]))
        return dict(row)

    # proposed additions to the fact bank, waiting for the user

    def add_proposal(self, *, experience: str, kind: str, text: str, target: str = "", reason: str = "",
                     job_key: str = "", now: datetime | None = None) -> bool:
        """Record a proposal. False when the same proposal already exists, whatever its status."""
        with self.tx() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO proposals (job_key, experience, kind, target, text, reason, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (job_key, experience, kind, target, text, reason[:300], iso(now or datetime.now().astimezone())))
            return cur.rowcount == 1

    def proposals(self, status: str = "pending") -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM proposals WHERE status=? ORDER BY id", (status,))
        return [dict(r) for r in rows]

    def get_proposal(self, proposal_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        return dict(row) if row else None

    def decide_proposal(self, proposal_id: int, status: str, now: datetime | None = None) -> None:
        if status not in ("approved", "rejected"):
            raise ValueError("status must be approved or rejected")
        with self.tx() as c:
            c.execute("UPDATE proposals SET status=?, decided_at=? WHERE id=?",
                      (status, iso(now or datetime.now().astimezone()), proposal_id))

    # replies from employers

    def save_email(self, thread_id: str, *, received: str, from_addr: str, subject: str, kind: str, company: str,
                   job_key: str, summary: str, now: datetime | None = None) -> bool:
        """Store one classified message. False when the thread was already stored."""
        with self.tx() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO emails (thread_id, received, from_addr, subject, kind, company, job_key, "
                "summary, handled_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (thread_id, received, from_addr[:200], subject[:300], kind, company[:200], job_key, summary[:500],
                 iso(now or datetime.now().astimezone())))
            return cur.rowcount == 1

    def emails(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM emails ORDER BY received DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # key value metadata

    def get_meta(self, key: str, default: str = "") -> str:
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO meta (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (key, value))

    def set_meta_json(self, key: str, value: Any) -> None:
        self.set_meta(key, json.dumps(value))

    def get_meta_json(self, key: str, default: Any = None) -> Any:
        raw = self.get_meta(key)
        return json.loads(raw) if raw else default
