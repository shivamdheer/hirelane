"""Paths and settings.

Everything the user owns lives under one home directory (``HIRELANE_HOME``, default ``~/.hirelane``):
``config/`` for YAML the user edits, ``data/`` for the database and run artifacts, ``resumes/`` for the PDFs.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, fields
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

HOME_ENV = "HIRELANE_HOME"
DEMO_HOME_ENV = "HIRELANE_DEMO_HOME"
LIVE_ENV = "HIRELANE_ALLOW_LIVE"
KEYRING_SERVICE = "hirelane"

SUBMIT_MODES = ("review", "live")
AUTO_APPROVE_MODES = ("none", "fit_a")
AI_PROVIDERS = ("none", "anthropic", "openai", "compatible")
LOCATION_SCOPES = ("anywhere", "country", "regions")

DEFAULT_DAILY_CAP = 10
DEFAULT_WEB_PORT = 8766
MAX_DAILY_CAP = 50
MAX_TARGET = 50


def home_dir() -> Path:
    return Path(os.environ.get(HOME_ENV) or Path.home() / ".hirelane").expanduser()


@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def config(self) -> Path:
        return self.home / "config"

    @property
    def experience(self) -> Path:
        return self.config / "experience"

    @property
    def data(self) -> Path:
        return self.home / "data"

    @property
    def db(self) -> Path:
        return self.data / "hirelane.db"

    @property
    def runs(self) -> Path:
        return self.data / "runs"

    @property
    def resumes(self) -> Path:
        return self.home / "resumes"

    @property
    def settings_file(self) -> Path:
        return self.config / "settings.yaml"

    @property
    def profile_file(self) -> Path:
        return self.config / "profile.yaml"

    @property
    def answers_file(self) -> Path:
        return self.config / "answers.yaml"

    @property
    def companies_file(self) -> Path:
        return self.config / "companies.yaml"

    def ensure(self) -> Paths:
        for d in (self.config, self.experience, self.data, self.runs, self.resumes):
            d.mkdir(parents=True, exist_ok=True)
        return self
