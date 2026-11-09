"""Checks that explain why something is not working. Each check returns a level and a plain sentence."""
from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass

from . import facts, secrets
from .config import Paths, load_settings
from .profile import ProfileError, load_profile

OK, WARN, FAIL = "ok", "warn", "fail"
MIN_FREE_BYTES = 500_000_000


@dataclass(frozen=True)
class Finding:
    level: str
    check: str
    message: str


def run_checks(paths: Paths) -> list[Finding]:
    out: list[Finding] = []

    def add(level: str, check: str, message: str) -> None:
        out.append(Finding(level, check, message))

    try:
        settings = load_settings(paths.settings_file)
        add(OK, "settings", f"mode {settings.submit_mode}, daily cap {settings.daily_cap}")
    except ValueError as e:
        add(FAIL, "settings", str(e))
        return out
    try:
        profile = load_profile(paths.profile_file)
        add(OK, "profile", f"{profile.name}, {len(profile.tracks)} track(s)")
        if not profile.tracks:
            add(WARN, "tracks", "no tracks yet, so no role will match. Add one to config/profile.yaml")
    except ProfileError as e:
        add(FAIL, "profile", str(e))
    try:
        bank = facts.load_bank(paths.experience)
        n = sum(len(e.bullets) for e in bank.experiences)
        noun = "experience" if len(bank.experiences) == 1 else "experiences"
        add(OK if n else WARN, "facts", f"{len(bank.experiences)} {noun}, {n} approved bullet{'' if n == 1 else 's'}")
    except facts.FactsError as e:
        add(FAIL, "facts", str(e))
    if settings.ai.provider == "none":
        add(OK, "ai", "off, using the deterministic scorer and approved wording only")
    elif settings.ai.provider != "compatible" and not secrets.get_secret(secrets.AI_KEY):
        add(WARN, "ai", f"provider {settings.ai.provider} has no key, run `hirelane set-key ai-api-key`")
    elif not settings.ai.model:
        add(WARN, "ai", "set ai.model in config/settings.yaml")
    else:
        add(OK, "ai", f"provider {settings.ai.provider}")
    if importlib.util.find_spec("playwright") is None:
        add(WARN, "browser", "Playwright is not installed, so forms cannot be filled. "
                             "Install it with pip install 'hirelane[browser]'")
    else:
        add(OK, "browser", "Playwright is installed. Run `playwright install chromium` once if forms fail to open")
    add(OK, "google", "connected" if settings.google_enabled else "not connected, optional")
    free = shutil.disk_usage(paths.home if paths.home.exists() else paths.home.parent).free
    add(OK if free > MIN_FREE_BYTES else WARN, "disk", f"{free // 1_000_000} MB free")
    return out
