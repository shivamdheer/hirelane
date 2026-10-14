"""Small text helpers used across modules. No I/O."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

LEGAL_SUFFIXES = {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co", "plc", "lp", "llp",
                  "gmbh", "sa", "ag", "pbc"}
# Dropped only when comparing company names, never in file names.
SOFT_SUFFIXES = LEGAL_SUFFIXES | {"group", "holdings", "technologies", "technology", "systems", "software",
                                  "labs", "company", "the", "hq", "global", "usa", "us", "na"}
TRACKING_PARAMS = {"gh_src", "lever-source", "lever-origin", "source", "src", "ref", "referrer", "trk", "trkid",
                   "lever-source[]", "ashby_jid_src", "utm", "fbclid", "gclid", "mc_cid", "mc_eid", "_hsenc", "_hsmi"}
BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "section",
              "article", "header", "footer", "blockquote", "pre", "hr"}
MAX_JD_CHARS = 40_000
# Separator inside a range such as "3-5 years" or "$90K to $110K", including the typographic dashes.
RANGE_SEP = r"(?:-|to|\N{EN DASH}|\N{EM DASH})"
MAX_FILE_KEY = 60
MIN_LETTERS_TO_JUDGE = 40
ENGLISH_ASCII_RATIO = 0.9
ENGLISH_STOPWORD_RATIO = 0.08

_STOPWORDS = {"the", "and", "to", "of", "a", "in", "for", "with", "you", "we", "our", "is", "are", "on", "as",
              "will", "be", "your", "or", "an", "this", "that", "at", "by", "from", "experience", "work", "team"}
_FOREIGN_STOPWORDS = {"und", "der", "die", "das", "wir", "mit", "für", "ein", "eine", "sie", "ihre", "nous", "vous",
                      "les", "des", "pour", "avec", "est", "el", "los", "las", "para", "con", "una", "del", "que",
                      "por", "het", "een", "voor", "il", "di", "della", "che", "per", "och", "att"}


def _ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def file_key(company: str) -> str:
    """Company name to a file name key of ASCII letters and digits. Never empty.

    'AT&T' becomes 'ATT', 'Caselle, Inc.' becomes 'Caselle'.
    """
    words = re.findall(r"[A-Za-z0-9&']+", _ascii_fold(company or ""))
    while len(words) > 1 and words[-1].lower().strip("'") in LEGAL_SUFFIXES:
        words.pop()
    key = re.sub(r"[^A-Za-z0-9]", "", "".join(words))
    if not key:
        key = "Company" + hashlib.sha1((company or "").encode(), usedforsecurity=False).hexdigest()[:4]
    return key[:MAX_FILE_KEY]


def norm_company(company: str) -> str:
    """Comparison form of a company name: 'Asure Software, Inc.' becomes 'asure'."""
    words = re.findall(r"[a-z0-9]+", _ascii_fold(company or "").lower().replace("&", " and "))
    core = [w for w in words if w not in SOFT_SUFFIXES]
    return "".join(core or words)


def norm_title(title: str) -> str:
    t = _ascii_fold(title or "").lower()
    t = re.sub(r"\bsr\b\.?", "senior", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def strip_tracking(url: str) -> str:
    """Remove tracking query parameters and keep functional ones such as gh_jid."""
    if not url:
        return url
    parts = urlsplit(url.strip())
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def host_matches(host: str, domain: str) -> bool:
    host, domain = host.lower().rstrip("."), domain.lower()
    return host == domain or host.endswith("." + domain)


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str, limit: int = MAX_JD_CHARS) -> str:
    """HTML to plain text. Greenhouse returns its HTML entity escaped, so that case is unescaped first."""
    if not raw:
        return ""
    s = raw
    if "&lt;" in s[:2000] and "<" not in s[:200]:
        s = html.unescape(s)
    parser = _Stripper()
    try:
        parser.feed(s)
        parser.close()
        text = "".join(parser.parts)
    except (ValueError, AssertionError):  # malformed HTML falls back to a plain tag strip
        text = re.sub(r"<[^>]+>", " ", s)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text[:limit]


def is_english(text: str) -> bool:
    sample = (text or "")[:4000]
    letters = [c for c in sample if c.isalpha()]
    if len(letters) < MIN_LETTERS_TO_JUDGE:
        return True
    ascii_ratio = sum(1 for c in letters if c.isascii()) / len(letters)
    words = re.findall(r"[a-zA-Z]+", sample.lower())
    stop_ratio = sum(1 for w in words if w in _STOPWORDS) / max(len(words), 1)
    foreign = sum(1 for w in re.findall(r"[^\W\d_]+", sample.lower()) if w in _FOREIGN_STOPWORDS) / max(len(words), 1)
    return ascii_ratio > ENGLISH_ASCII_RATIO and stop_ratio > ENGLISH_STOPWORD_RATIO and foreign < stop_ratio / 2
