"""Gmail: read recent employer mail for reply tracking, and send the daily digest to the user's own address."""
from __future__ import annotations

import base64
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Any

from ..inbox import Message
from ..profile import Profile

QUERY = "newer_than:2d -category:promotions -category:social -in:sent"
MAX_RESULTS = 50
MAX_BODY_CHARS = 6000


def _header(payload: dict[str, Any], name: str) -> str:
    for h in payload.get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return str(h.get("value", ""))
    return ""


def _decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", "replace")


def _text_of(payload: dict[str, Any]) -> str:
    """The first plain text part, searching nested parts. HTML-only mail yields an empty string."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])
    for part in payload.get("parts", []) or []:
        found = _text_of(part)
        if found:
            return found
    return ""


def to_message(raw: dict[str, Any]) -> Message:
    payload = raw.get("payload", {})
    date = _header(payload, "Date")
    try:
        received = parsedate_to_datetime(date).isoformat()
    except (TypeError, ValueError):
        received = ""
    return Message(thread_id=str(raw.get("threadId") or raw.get("id", "")), received=received,
                   from_addr=_header(payload, "From"), subject=_header(payload, "Subject"),
                   body=_text_of(payload)[:MAX_BODY_CHARS])


def fetch_messages(svc: Any, query: str = QUERY, limit: int = MAX_RESULTS) -> list[Message]:
    """Recent messages, one per thread. The service is a googleapiclient Gmail resource."""
    listing = svc.users().messages().list(userId="me", q=query, maxResults=limit).execute()
    seen: set[str] = set()
    out: list[Message] = []
    for ref in listing.get("messages", []) or []:
        if ref.get("threadId") in seen:
            continue
        seen.add(ref.get("threadId", ""))
        raw = svc.users().messages().get(userId="me", id=ref["id"], format="full").execute()
        out.append(to_message(raw))
    return out


def send_digest(svc: Any, profile: Profile, subject: str, body: str) -> None:
    """Send the digest to the profile's own address. There is no parameter for another recipient."""
    msg = EmailMessage()
    msg["To"] = profile.email
    msg["From"] = profile.email
    msg["Subject"] = subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    svc.users().messages().send(userId="me", body={"raw": raw}).execute()
