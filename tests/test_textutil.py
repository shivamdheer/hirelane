from __future__ import annotations

import pytest

from hirelane import textutil as T


@pytest.mark.parametrize("name,key", [
    ("AT&T", "ATT"),
    ("Caselle, Inc.", "Caselle"),
    ("Northwind Labs LLC", "NorthwindLabs"),
    ("L'Oréal", "LOreal"),
])
def test_file_key(name: str, key: str) -> None:
    assert T.file_key(name) == key


def test_file_key_is_never_empty() -> None:
    assert T.file_key("!!!").startswith("Company")


def test_norm_company_drops_soft_suffixes() -> None:
    assert T.norm_company("Asure Software, Inc.") == "asure"
    assert T.norm_company("The Fabrikam Group") == "fabrikam"


def test_norm_title_expands_sr() -> None:
    assert T.norm_title("Sr. Data Analyst") == "senior data analyst"


def test_strip_tracking_keeps_functional_params() -> None:
    url = "https://boards.example.com/jobs/1?gh_jid=42&utm_source=x&gh_src=abc"
    assert T.strip_tracking(url) == "https://boards.example.com/jobs/1?gh_jid=42"


def test_host_matches_requires_label_boundary() -> None:
    assert T.host_matches("boards.greenhouse.io", "greenhouse.io")
    assert not T.host_matches("evilgreenhouse.io", "greenhouse.io")


def test_html_to_text_handles_escaped_markup_and_lists() -> None:
    raw = "&lt;p&gt;Build things&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;/ul&gt;"
    text = T.html_to_text(raw)
    assert "Build things" in text
    assert "- Python" in text and "- SQL" in text


def test_html_to_text_drops_scripts() -> None:
    assert "alert" not in T.html_to_text("<p>Hello</p><script>alert(1)</script>")


def test_is_english() -> None:
    en = "We are looking for an analyst to join our team and work with the data for our customers every day. " * 3
    de = "Wir suchen einen Analysten für unser Team und die Zusammenarbeit mit der Abteilung und mit den Kunden. " * 3
    assert T.is_english(en)
    assert not T.is_english(de)
