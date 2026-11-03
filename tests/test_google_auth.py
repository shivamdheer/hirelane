from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest

from hirelane import secrets
from hirelane.google import auth

CLIENT = {"installed": {"client_id": "id.apps.example.com", "client_secret": "shh",
                        "auth_uri": "https://accounts.example.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.example.com/token"}}


def test_client_file_must_be_a_desktop_client() -> None:
    assert auth.validate_client_config(CLIENT) == CLIENT
    for bad in ({}, {"web": CLIENT["installed"]}, {"installed": {"client_id": "x"}}):
        with pytest.raises(auth.GoogleError, match="desktop app OAuth client"):
            auth.validate_client_config(bad)


def test_connect_stores_client_and_token_in_the_keyring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Creds:
        def to_json(self) -> str:
            return '{"token": "t"}'

    class Flow:
        scopes: ClassVar[list[str]] = []

        @classmethod
        def from_client_config(cls, config: dict, scopes: list[str]) -> Flow:
            cls.scopes = scopes
            return cls()

        def run_local_server(self, port: int, open_browser: bool) -> Creds:
            return Creds()

    monkeypatch.setattr(auth, "_flow_cls", lambda: Flow)
    f = tmp_path / "client.json"
    f.write_text(json.dumps(CLIENT))
    assert not auth.is_connected()
    auth.connect(f)
    assert auth.is_connected()
    assert json.loads(secrets.get_secret(secrets.GOOGLE_CLIENT) or "") == CLIENT
    assert Flow.scopes == list(auth.SCOPES)
    auth.disconnect()
    assert not auth.is_connected()


def test_unreadable_client_files_are_reported(tmp_path: Path) -> None:
    with pytest.raises(auth.GoogleError, match="could not read"):
        auth.connect(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    with pytest.raises(auth.GoogleError, match="could not read"):
        auth.connect(bad)


def test_credentials_require_a_connection() -> None:
    with pytest.raises(auth.GoogleError, match="hirelane google connect"):
        auth.credentials()


def test_scopes_are_the_minimum_the_features_need() -> None:
    assert any(s.endswith("gmail.readonly") for s in auth.SCOPES)
    assert not any(s.endswith("/gmail.modify") or s.endswith("/mail.google.com/") for s in auth.SCOPES)
    assert not any(s.endswith("/calendar") or s.endswith("calendar.events") for s in auth.SCOPES)
