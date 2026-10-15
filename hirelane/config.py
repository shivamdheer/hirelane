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


def get_paths() -> Paths:
    return Paths(home_dir())


@dataclass(frozen=True)
class AiSettings:
    provider: str = "none"
    model: str = ""
    base_url: str = ""            # only for provider "compatible", for example a local Ollama server
    timeout_s: int = 120
    max_calls_per_run: int = 40


@dataclass(frozen=True)
class Settings:
    submit_mode: str = "review"
    daily_cap: int = DEFAULT_DAILY_CAP
    delay_min_s: int = 20
    delay_max_s: int = 75
    daily_target: int = 10
    auto_approve: str = "none"    # none: you approve each job. fit_a: strong matches are approved for you
    posted_within_days: int = 7
    web_port: int = DEFAULT_WEB_PORT
    timezone: str = ""            # IANA name, empty means the system zone
    headless: bool = True
    google_enabled: bool = False
    ai: AiSettings = field(default_factory=AiSettings)

    def validate(self) -> Settings:
        if self.submit_mode not in SUBMIT_MODES:
            raise ValueError(f"submit_mode must be one of {SUBMIT_MODES}, got {self.submit_mode!r}")
        if self.auto_approve not in AUTO_APPROVE_MODES:
            raise ValueError(f"auto_approve must be one of {AUTO_APPROVE_MODES}, got {self.auto_approve!r}")
        if not 0 <= self.daily_cap <= MAX_DAILY_CAP:
            raise ValueError(f"daily_cap must be between 0 and {MAX_DAILY_CAP}")
        if not 1 <= self.daily_target <= MAX_TARGET:
            raise ValueError(f"daily_target must be between 1 and {MAX_TARGET}")
        if self.delay_min_s < 0 or self.delay_min_s > self.delay_max_s:
            raise ValueError("delay_min_s must be between 0 and delay_max_s")
        if self.posted_within_days < 1:
            raise ValueError("posted_within_days must be at least 1")
        if self.ai.provider not in AI_PROVIDERS:
            raise ValueError(f"ai.provider must be one of {AI_PROVIDERS}, got {self.ai.provider!r}")
        if self.ai.provider == "compatible" and not self.ai.base_url:
            raise ValueError("ai.base_url is required when ai.provider is compatible")
        if self.timezone:
            ZoneInfo(self.timezone)
        return self


def _coerce(raw: dict[str, Any]) -> Settings:
    allowed = {f.name for f in fields(Settings)} - {"ai"}
    values = {k: v for k, v in raw.items() if k in allowed}
    ai_raw = raw.get("ai") or {}
    ai_allowed = {f.name for f in fields(AiSettings)}
    ai = AiSettings(**{k: v for k, v in ai_raw.items() if k in ai_allowed})
    return Settings(**values, ai=ai)


def load_settings(path: Path | None = None) -> Settings:
    p = path or get_paths().settings_file
    raw = yaml.safe_load(p.read_text()) if p.exists() else {}
    return _coerce(raw or {}).validate()


def save_setting(key: str, value: Any, path: Path | None = None) -> None:
    """Change one top-level key and keep the comments in the file.

    The file is replaced atomically so a reader never sees half of it.
    """
    p = path or get_paths().settings_file
    text = p.read_text() if p.exists() else ""
    raw = yaml.safe_load(text) or {}
    raw[key] = value
    _coerce(raw).validate()
    dumped = yaml.safe_dump({key: value}, default_flow_style=isinstance(value, (list, tuple)), sort_keys=False).strip()
    line = re.compile(rf"^{re.escape(key)}:[^\n#]*?(\s*#.*)?$", re.MULTILINE)
    if line.search(text):
        text = line.sub(lambda m: dumped + (m.group(1) or ""), text, count=1)
    else:
        text = text.rstrip("\n") + ("\n" if text else "") + dumped + "\n"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".yaml.tmp")
    tmp.write_text(text)
    os.replace(tmp, p)


def live_submit_allowed(settings: Settings) -> bool:
    """Live submission needs two switches: the setting and the environment variable."""
    return settings.submit_mode == "live" and os.environ.get(LIVE_ENV) == "1"


def local_tz(settings: Settings | None = None) -> tzinfo:
    name = settings.timezone if settings else ""
    if name:
        return ZoneInfo(name)
    tz = datetime.now().astimezone().tzinfo
    return tz if tz is not None else ZoneInfo("UTC")


def now(settings: Settings | None = None) -> datetime:
    return datetime.now(local_tz(settings))


def today_str(settings: Settings | None = None) -> str:
    return now(settings).strftime("%Y-%m-%d")
