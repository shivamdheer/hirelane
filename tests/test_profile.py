from __future__ import annotations

import copy

import pytest
import yaml

from hirelane.config import Paths
from hirelane.profile import ProfileError, load_profile, parse_profile
from tests.profile_fixture import ALEX_PROFILE


def test_parse_alex() -> None:
    p = parse_profile(ALEX_PROFILE)
    assert p.first_name == "Alex" and p.last_name == "Rivera"
    assert [t.name for t in p.tracks] == ["data", "ops"]
    assert p.track("ops") is not None and p.track("ops").exclude_titles == ("sales",)  # type: ignore[union-attr]
    assert p.salary.floor == 60000
    assert p.level.allow_titles == ("associate product manager",)


def test_defaults_for_a_minimal_profile() -> None:
    p = parse_profile({"name": "Sam Lee", "email": "sam@example.com"})
    assert p.level.max_years == 2
    assert p.search.scope == "country"
    assert p.tracks == ()


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("email"),
    lambda d: d.update(email="not-an-email"),
    lambda d: d["tracks"].append(copy.deepcopy(d["tracks"][0])),
    lambda d: d["tracks"][0].pop("titles"),
    lambda d: d["search"].update(scope="moon"),
])
def test_invalid_profiles(mutate) -> None:
    raw = copy.deepcopy(ALEX_PROFILE)
    mutate(raw)
    with pytest.raises(ProfileError):
        parse_profile(raw)


def test_load_missing_profile_points_to_init(home: Paths) -> None:
    with pytest.raises(ProfileError, match="hirelane init"):
        load_profile()


def test_load_from_disk(home: Paths) -> None:
    home.profile_file.write_text(yaml.safe_dump(ALEX_PROFILE))
    assert load_profile().email == "alex.rivera@example.com"
