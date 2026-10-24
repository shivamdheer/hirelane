from __future__ import annotations

import pytest

from hirelane.submit.optmatch import match_option, norm_value


@pytest.mark.parametrize("answer,options,expected", [
    ("Yes", ["Yes", "No"], "Yes"),
    ("yes", ["Yes, I am authorized", "No"], "Yes, I am authorized"),
    ("No", ["Yes", "No, I do not require sponsorship"], "No, I do not require sponsorship"),
    ("United States", ["Canada", "United States of America"], "United States of America"),
    ("Decline to self-identify", ["Male", "Female", "I don't wish to answer"], None),
    ("Web", ["Referral", "Web search"], "Web search"),
    ("", ["A"], None),
    ("Maybe", ["Yes", "No"], None),
])
def test_match_option(answer: str, options: list[str], expected: str | None) -> None:
    assert match_option(answer, options) == expected


def test_norm_value_collapses_whitespace_and_case() -> None:
    assert norm_value("  Hello \n World ") == "hello world"
