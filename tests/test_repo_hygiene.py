from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DASHES = (chr(0x2014), chr(0x2013))
PROSE_SUFFIXES = (".md", ".html", ".yml", ".yaml")


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [ROOT / f for f in out.split() if Path(f).suffix not in (".png", ".pdf", ".ico")]


def test_no_dash_characters_in_tracked_text_files() -> None:
    offenders = [f.name for f in tracked_files() if any(d in f.read_text() for d in DASHES)]
    assert offenders == []


def test_no_semicolons_in_markdown_prose() -> None:
    bad = []
    for f in tracked_files():
        if f.suffix != ".md":
            continue
        in_code = False
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if line.startswith("```"):
                in_code = not in_code
            elif not in_code and "; " in line:
                bad.append(f"{f.name}:{n}")
    assert bad == []


def test_no_secrets_or_local_data_are_tracked() -> None:
    names = {f.name for f in tracked_files()}
    assert not names & {".env", "token.json", "hirelane.db", "answers.yaml", "profile.yaml"} or all(
        "templates" in str(f) for f in tracked_files() if f.name in ("answers.yaml", "profile.yaml"))
    assert not any(f.suffix == ".db" for f in tracked_files())


def test_templates_parse_as_yaml_with_placeholders_filled() -> None:
    import yaml

    from hirelane.init import TEMPLATES
    for t in TEMPLATES.glob("*.yaml"):
        text = t.read_text()
        for key in ("name", "email", "phone", "city", "region", "country", "postal_code", "links", "tracks",
                    "needs_sponsorship", "degree", "rules"):
            text = text.replace("{{" + key + "}}", "x" if key not in ("links", "tracks", "rules") else "")
        yaml.safe_load(text)
