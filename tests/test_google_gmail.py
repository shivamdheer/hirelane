from __future__ import annotations

import base64
import email
from typing import Any

from hirelane.google import gmail
from hirelane.profile import parse_profile
from tests.profile_fixture import ALEX_PROFILE


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def raw_message(thread: str, body: str, subject: str = "Hello", sender: str = "jobs@fabrikam.example.com",
                nested: bool = False) -> dict[str, Any]:
    part = {"mimeType": "text/plain", "body": {"data": b64(body)}}
    payload: dict[str, Any] = {"headers": [{"name": "From", "value": sender}, {"name": "Subject", "value": subject},
                                           {"name": "Date", "value": "Tue, 10 Mar 2026 09:30:00 -0500"}]}
    if nested:
        payload.update(mimeType="multipart/mixed", parts=[{"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/html", "body": {"data": b64("<p>hi</p>")}}, part]}])
    else:
        payload.update(part)
    return {"id": f"m-{thread}", "threadId": thread, "payload": payload}


class FakeGmail:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.store = {m["id"]: m for m in messages}
        self.sent: list[dict[str, Any]] = []
        self.queries: list[str] = []

    def users(self) -> FakeGmail:
        return self

    def messages(self) -> FakeGmail:
        return self          # googleapiclient style chaining: users().messages().list(...).execute()

    def list(self, userId: str, q: str, maxResults: int) -> Any:
        self.queries.append(q)
        refs = [{"id": m["id"], "threadId": m["threadId"]} for m in self.store.values()]
        return _Exec({"messages": refs})

    def get(self, userId: str, id: str, format: str) -> Any:
        return _Exec(self.store[id])

    def send(self, userId: str, body: dict[str, Any]) -> Any:
        self.sent.append(body)
        return _Exec({})


class _Exec:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def execute(self) -> dict[str, Any]:
        return self.value


def test_to_message_reads_headers_and_body() -> None:
    m = gmail.to_message(raw_message("t1", "We regret to inform you.", "Update"))
    assert (m.thread_id, m.subject, m.from_addr) == ("t1", "Update", "jobs@fabrikam.example.com")
    assert m.body == "We regret to inform you." and m.received.startswith("2026-03-10T09:30:00")


def test_nested_multipart_prefers_plain_text() -> None:
    m = gmail.to_message(raw_message("t2", "Plain part", nested=True))
    assert m.body == "Plain part"


def test_fetch_messages_dedupes_threads() -> None:
    svc = FakeGmail([raw_message("t1", "a"), {**raw_message("t1", "b"), "id": "m-t1b"}, raw_message("t2", "c")])
    out = gmail.fetch_messages(svc)
    assert [m.thread_id for m in out] == ["t1", "t2"]
    assert "-in:sent" in svc.queries[0]


def test_digest_goes_only_to_the_profile_address() -> None:
    svc = FakeGmail([])
    profile = parse_profile(ALEX_PROFILE)
    gmail.send_digest(svc, profile, "hirelane 2026-03-10: nothing new", "Nothing new today.\n")
    (sent,) = svc.sent
    msg = email.message_from_bytes(base64.urlsafe_b64decode(sent["raw"]))
    assert msg["To"] == "alex.rivera@example.com" and msg["Subject"].startswith("hirelane")
    assert "Nothing new today." in msg.get_payload()  # type: ignore[operator]
