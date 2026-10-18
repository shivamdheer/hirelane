from __future__ import annotations

from datetime import date

import pytest

from hirelane import filters, level
from hirelane.models import Posting
from hirelane.profile import LevelRules, SearchRules, parse_profile
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)
RULES = LevelRules()


def p(title: str = "Data Analyst", location: str = "Chicago, IL", **kw: object) -> Posting:
    return Posting(ats="greenhouse", slug="fabrikam", job_id="1", company="Fabrikam", title=title, location=location,
                   **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("title,expected", [
    ("Senior Data Analyst", "senior"),
    ("Sr. Analyst", "sr"),
    ("Data Analyst II", "II"),
    ("Analytics Manager", "manager"),
    ("Data Analyst", ""),
    ("Associate Product Manager", "manager"),
])
def test_senior_word_in_title(title: str, expected: str) -> None:
    assert level.senior_word_in_title(title, RULES) == expected


def test_allow_titles_override_senior_words() -> None:
    assert level.senior_word_in_title("Associate Product Manager", PROFILE.level) == ""


@pytest.mark.parametrize("desc,low,high", [
    ("3+ years of experience with SQL", 3, 3),
    ("2-5 years of professional experience", 2, 5),
    ("Minimum 4 years", 4, 4),
    ("5 years of experience preferred", None, None),
    ("Great team, free lunch", None, None),
])
def test_years_asked(desc: str, low: int | None, high: int | None) -> None:
    assert level.years_asked(desc) == (low, high)


def test_assess_uses_the_users_limit() -> None:
    desc = "You have 3 years of experience in analytics."
    assert not level.assess("Data Analyst", desc, LevelRules(max_years=2)).keep
    assert level.assess("Data Analyst", desc, LevelRules(max_years=3)).keep
    assert level.assess("Data Analyst", "", LevelRules()).keep


def test_match_track_prefers_the_longest_phrase_and_respects_excludes() -> None:
    assert filters.match_track("Junior Data Analyst", PROFILE).name == "data"  # type: ignore[union-attr]
    assert filters.match_track("Business Analyst", PROFILE).name == "ops"  # type: ignore[union-attr]
    assert filters.match_track("Sales Operations Analyst", PROFILE) is None
    assert filters.match_track("Chef", PROFILE) is None


@pytest.mark.parametrize("location,remote,ok", [
    ("Chicago, IL", False, True),
    ("Remote - US", True, True),
    ("Remote", True, True),
    ("Toronto, Canada", False, False),
    ("London, United Kingdom", False, False),
    ("Remote, India", True, False),
])
def test_location_country_scope(location: str, remote: bool, ok: bool) -> None:
    assert filters.location_ok(p(location=location, remote=remote), SearchRules())[0] is ok


def test_location_regions_scope_and_remote_toggle() -> None:
    rules = SearchRules(scope="regions", regions=("illinois", ", il"), include_remote=False)
    assert filters.location_ok(p(location="Chicago, IL"), rules)[0]
    assert not filters.location_ok(p(location="Austin, TX"), rules)[0]
    assert not filters.location_ok(p(location="Remote - US", remote=True), rules)[0]


def test_remote_excluded_in_country_scope() -> None:
    ok, why = filters.location_ok(p(location="Remote - US", remote=True), SearchRules(include_remote=False))
    assert not ok and "remote" in why


def test_anywhere_scope_accepts_everything() -> None:
    assert filters.location_ok(p(location="Lagos"), SearchRules(scope="anywhere"))[0]


def test_fresh() -> None:
    today = date(2026, 3, 10)
    assert filters.fresh(p(posted="2026-03-08"), 7, today)
    assert not filters.fresh(p(posted="2026-02-20"), 7, today)
    assert filters.fresh(p(posted=""), 7, today)


def test_check_title_then_description() -> None:
    assert filters.check_title(p("Pastry Chef"), PROFILE).reason.startswith("title")
    v = filters.check_title(p("Data Analyst"), PROFILE)
    assert v.keep and v.track == "data"
    late = p("Data Analyst", description="Requires 6 years of experience.", posted="2026-03-09")
    assert "years" in filters.check_description(late, PROFILE, 7, date(2026, 3, 10)).reason
    stale = p("Data Analyst", posted="2026-01-01")
    assert filters.check_description(stale, PROFILE, 7, date(2026, 3, 10)).reason.startswith("freshness")


def test_description_checks_apply_pay_floor_and_knockouts() -> None:
    today = date(2026, 3, 10)
    low_pay = p("Data Analyst", pay="$30,000 - $40,000", posted="2026-03-09")
    assert filters.check_description(low_pay, PROFILE, 7, today).reason.startswith("pay")
    ko = p("Data Analyst", description="Commission only role.", posted="2026-03-09")
    assert filters.check_description(ko, PROFILE, 7, today).reason.startswith("not eligible")
    good = p("Data Analyst", description="SQL and dashboards.", posted="2026-03-09")
    assert filters.check_description(good, PROFILE, 7, today).keep
