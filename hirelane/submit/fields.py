"""A generic model of an application form: scan it into fields, fill one field, read the values back.

The scanner tags each question with a ``data-af-id`` attribute and never changes a value. Values are only ever set by
Playwright with real input events, so the page's own scripts see what a person would have typed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .optmatch import YES_WORDS, match_option, norm_value

JS_DIR = Path(__file__).parent / "js"
SCAN_JS = (JS_DIR / "scan.js").read_text()
PAGE_ERRORS_JS = (JS_DIR / "page_errors.js").read_text()
SETTLE_MS = 250
FIELD_TIMEOUT_MS = 10_000
OPTION_POLLS = 12
OPTION_POLL_MS = 250
MIN_PHONE_DIGITS = 7




@dataclass
class FormField:
    fid: str
    label: str
    # text, email, tel, url, number, date, textarea, select, combobox, radio, checkbox, checkboxes or file
    kind: str
    required: bool = False
    options: list[str] = field(default_factory=list)
    value: str = ""
    maxlength: int = 0


def scan(page: Any) -> list[FormField]:
    rows = page.evaluate(SCAN_JS)
    return [FormField(r["fid"], r["label"], r["kind"], bool(r["required"]), list(r["options"]), r["value"],
                      int(r["maxlength"])) for r in rows]


def page_errors(page: Any) -> list[str]:
    return list(page.evaluate(PAGE_ERRORS_JS))


def values_match(expected: str, actual: str) -> bool:
    e, a = norm_value(expected), norm_value(actual)
    if e == a:
        return True
    digits_e, digits_a = re.sub(r"\D", "", e), re.sub(r"\D", "", a)
    return bool(digits_e) and digits_e == digits_a and len(digits_e) >= MIN_PHONE_DIGITS  # phone, another format


def _locator(page: Any, f: FormField) -> Any:
    return page.locator(f'[data-af-id="{f.fid}"]').first


def fill_field(page: Any, f: FormField, value: str) -> str | None:
    """Set one field the way a person would. Returns a problem description or None."""
    loc = _locator(page, f)
    try:
        if f.kind in ("text", "email", "tel", "url", "number", "date", "textarea"):
            loc.scroll_into_view_if_needed(timeout=FIELD_TIMEOUT_MS)
            loc.fill(value, timeout=FIELD_TIMEOUT_MS)
        elif f.kind == "select":
            choice = match_option(value, f.options)
            if choice is None:
                return f"no option for {value!r} in {f.options[:6]}"
            loc.select_option(label=choice, timeout=FIELD_TIMEOUT_MS)
        elif f.kind in ("radio", "checkboxes"):
            choice = match_option(value, f.options)
            if choice is None:
                return f"no option for {value!r} in {f.options[:6]}"
            index = f.options.index(choice)
            page.locator(f'[data-af-opt="{f.fid}:{index}"]').first.check(timeout=FIELD_TIMEOUT_MS)
        elif f.kind == "checkbox":
            if norm_value(value) in YES_WORDS:
                loc.check(timeout=FIELD_TIMEOUT_MS)
            else:
                loc.uncheck(timeout=FIELD_TIMEOUT_MS)
        elif f.kind == "combobox":
            return _fill_combobox(page, loc, value)
        else:
            return f"cannot fill a {f.kind} field"
    except Exception as e:  # Playwright raises its own TimeoutError and Error types
        return f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"
    page.wait_for_timeout(SETTLE_MS)
    return None


def _fill_combobox(page: Any, loc: Any, value: str) -> str | None:
    loc.click(timeout=FIELD_TIMEOUT_MS)
    loc.fill(value, timeout=FIELD_TIMEOUT_MS)
    for _ in range(OPTION_POLLS):
        options = page.locator('[role="option"]')
        texts = [t.strip() for t in options.all_inner_texts()]
        choice = match_option(value, texts)
        if choice is not None:
            options.nth(texts.index(choice)).click(timeout=FIELD_TIMEOUT_MS)
            return None
        page.wait_for_timeout(OPTION_POLL_MS)
    return f"no dropdown option for {value!r}"


def attach_file(page: Any, f: FormField, path: str) -> str | None:
    try:
        _locator(page, f).set_input_files(path, timeout=FIELD_TIMEOUT_MS)
    except Exception as e:
        return f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"
    page.wait_for_timeout(SETTLE_MS)
    return None
