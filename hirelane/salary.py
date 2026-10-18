"""Reading posted pay ranges and comparing them with the user's own floor."""
from __future__ import annotations

import re

NUMBER_TOKEN = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{2,3}(?:\.\d+)?|\d{4,6})\s?([kK]\b)?")
HOURLY = re.compile(r"\b(?:hour|hr)\b|/h\b", re.I)
MIN_ANNUAL = 20_000
THOUSAND = 1000


def pay_range(pay: str) -> tuple[int | None, int | None]:
    """The lowest and highest annual dollar figure in a pay text such as "$90,000 - $110,000" or "$70-85K".

    Hourly rates and texts without a dollar sign are ignored.
    """
    text = pay or ""
    if "$" not in text or HOURLY.search(text):
        return None, None
    tokens = [(m.group(1).replace(",", ""), bool(m.group(2))) for m in NUMBER_TOKEN.finditer(text)]
    has_k = any(k for _n, k in tokens)
    values: list[int] = []
    for raw, k in tokens:
        try:
            v = float(raw)
        except ValueError:
            continue
        values.append(int(v * THOUSAND) if (k or (has_k and v < THOUSAND)) else int(v))
    values = [v for v in values if v >= MIN_ANNUAL]
    return (min(values), max(values)) if values else (None, None)


def below_floor(pay: str, floor: int) -> bool:
    """True only when a range is posted and even its top is under the floor. No pay text never drops a posting."""
    if floor <= 0:
        return False
    _lo, hi = pay_range(pay)
    return hi is not None and hi < floor
