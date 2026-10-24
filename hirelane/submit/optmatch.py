"""Matching an answer to the options a form offers."""
from __future__ import annotations

import re

YES_WORDS = {"yes", "y", "true", "i agree", "agree", "i do", "i am", "i have", "1"}
NO_WORDS = {"no", "n", "false", "i do not", "i don't", "disagree", "0"}
MIN_PREFIX_KEY_LEN = 3


def norm_value(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "").replace("\N{NO-BREAK SPACE}", " ")).strip().lower()


def match_option(answer: str, options: list[str]) -> str | None:
    """The option that expresses the answer: same text, a yes or no synonym, or a prefix of it."""
    want = norm_value(answer)
    if not want:
        return None
    normed = {norm_value(o): o for o in options}
    if want in normed:
        return normed[want]
    if want in YES_WORDS or want in NO_WORDS:
        group = YES_WORDS if want in YES_WORDS else NO_WORDS
        for key, original in normed.items():
            if key in group or any(key.startswith(w + " ") or key.startswith(w + ",") for w in group):
                return original
    starts = [o for k, o in normed.items()
              if k.startswith(want) or (want.startswith(k) and len(k) >= MIN_PREFIX_KEY_LEN)]
    if len(starts) == 1:
        return starts[0]
    contains = [o for k, o in normed.items() if want in k]
    return contains[0] if len(contains) == 1 else None
