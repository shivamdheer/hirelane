from __future__ import annotations

import pytest

from hirelane import knockout, salary
from hirelane.profile import Knockouts


@pytest.mark.parametrize("text,expected", [
    ("$90,000 - $110,000", (90000, 110000)),
    ("$70-85K", (70000, 85000)),
    ("$120K to $150K", (120000, 150000)),
    ("$45 per hour", (None, None)),
    ("competitive pay", (None, None)),
    ("$25/hr - $30/hr", (None, None)),
])
def test_pay_range(text: str, expected: tuple[int | None, int | None]) -> None:
    assert salary.pay_range(text) == expected


def test_below_floor_needs_a_posted_range() -> None:
    assert salary.below_floor("$40,000 - $50,000", 60000)
    assert not salary.below_floor("$40,000 - $70,000", 60000)
    assert not salary.below_floor("", 60000)
    assert not salary.below_floor("$40,000 - $50,000", 0)


def test_sponsorship_only_matters_when_the_user_needs_it() -> None:
    desc = "We are unable to sponsor visas for this role."
    assert not knockout.check("Analyst", desc, Knockouts(needs_sponsorship=True)).eligible
    assert knockout.check("Analyst", desc, Knockouts(needs_sponsorship=False)).eligible


def test_clearance_and_citizenship() -> None:
    desc = "An active secret clearance is required."
    assert not knockout.check("Analyst", desc, Knockouts()).eligible
    assert knockout.check("Analyst", desc, Knockouts(has_clearance=True)).eligible
    mixed = "Must be a U.S. citizen or a permanent resident."
    assert knockout.check("Analyst", mixed, Knockouts()).eligible


def test_phd_requirement_depends_on_degree_held() -> None:
    desc = "A PhD is required for this position."
    assert not knockout.check("Scientist", desc, Knockouts(degree="masters")).eligible
    assert knockout.check("Scientist", desc, Knockouts(degree="phd")).eligible
    assert knockout.check("Scientist", "PhD preferred, master's or equivalent.", Knockouts(degree="masters")).eligible


def test_avoid_terms() -> None:
    v = knockout.check("Analyst", "This is a Commission Only position.", Knockouts(avoid_terms=("commission only",)))
    assert not v.eligible and "commission only" in v.reason
