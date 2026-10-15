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
