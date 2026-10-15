from __future__ import annotations

import pytest

from hirelane import config
from hirelane.config import Paths, Settings


def test_defaults_are_conservative(home: Paths) -> None:
    s = config.load_settings()
    assert s.submit_mode == "review"
    assert s.daily_cap == 10
    assert s.web_port == 8766
    assert s.ai.provider == "none"


def test_load_reads_nested_ai_section(home: Paths) -> None:
    home.settings_file.write_text("daily_cap: 5\nai:\n  provider: openai\n  model: some-model\n")
    s = config.load_settings()
    assert s.daily_cap == 5
    assert s.ai.provider == "openai"
    assert s.ai.model == "some-model"


@pytest.mark.parametrize("text", [
    "submit_mode: auto\n",
    "daily_cap: 500\n",
    "ai:\n  provider: mystery\n",
    "ai:\n  provider: compatible\n",
    "delay_min_s: 90\ndelay_max_s: 10\n",
])
def test_invalid_settings_are_rejected(home: Paths, text: str) -> None:
    home.settings_file.write_text(text)
    with pytest.raises(ValueError):
        config.load_settings()


def test_save_setting_keeps_comments(home: Paths) -> None:
    home.settings_file.write_text("# how many to submit\ndaily_cap: 10  # per day\nsubmit_mode: review\n")
    config.save_setting("daily_cap", 7)
    text = home.settings_file.read_text()
    assert "daily_cap: 7  # per day" in text
    assert text.startswith("# how many to submit")


def test_save_setting_rejects_bad_value_without_writing(home: Paths) -> None:
    home.settings_file.write_text("daily_cap: 10\n")
    with pytest.raises(ValueError):
        config.save_setting("daily_cap", 999)
    assert home.settings_file.read_text() == "daily_cap: 10\n"


def test_live_needs_both_switches(home: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    live = Settings(submit_mode="live")
    assert not config.live_submit_allowed(live)
    monkeypatch.setenv(config.LIVE_ENV, "1")
    assert config.live_submit_allowed(live)
    assert not config.live_submit_allowed(Settings())


def test_auto_approve_is_validated(home: Paths) -> None:
    home.settings_file.write_text("auto_approve: everything\n")
    with pytest.raises(ValueError, match="auto_approve"):
        config.load_settings()
    home.settings_file.write_text("auto_approve: fit_a\n")
    assert config.load_settings().auto_approve == "fit_a"
