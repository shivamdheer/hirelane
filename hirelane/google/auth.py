"""Connecting a Google account with the user's own OAuth client. Tokens are kept in the OS keyring."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import secrets

SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
)


class GoogleError(RuntimeError):
    pass


def _flow_cls() -> Any:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise GoogleError("install the google extra: pip install 'hirelane[google]'") from e
    return InstalledAppFlow


def validate_client_config(raw: dict[str, Any]) -> dict[str, Any]:
    """A desktop OAuth client file downloaded from the Google Cloud console."""
    section = raw.get("installed")
    if not isinstance(section, dict) or not section.get("client_id") or not section.get("client_secret"):
        raise GoogleError("that file is not a desktop app OAuth client, see docs/GOOGLE.md")
    return raw


def connect(client_file: Path) -> None:
    """Run the browser consent flow once and store the client and the token in the keyring."""
    try:
        config = validate_client_config(json.loads(client_file.read_text()))
    except (OSError, ValueError) as e:
        raise GoogleError(f"could not read the client file: {e}") from e
    flow = _flow_cls().from_client_config(config, scopes=list(SCOPES))
    creds = flow.run_local_server(port=0, open_browser=True)
    secrets.set_secret(secrets.GOOGLE_CLIENT, json.dumps(config))
    secrets.set_secret(secrets.GOOGLE_TOKEN, creds.to_json())


def disconnect() -> None:
    secrets.delete_secret(secrets.GOOGLE_TOKEN)
    secrets.delete_secret(secrets.GOOGLE_CLIENT)


def is_connected() -> bool:
    return bool(secrets.get_secret(secrets.GOOGLE_TOKEN))


def credentials() -> Any:
    """Stored credentials, refreshed when they have expired. Raises GoogleError when not connected."""
    raw = secrets.get_secret(secrets.GOOGLE_TOKEN)
    if not raw:
        raise GoogleError("Google is not connected, run `hirelane google connect`")
    try:
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise GoogleError("install the google extra: pip install 'hirelane[google]'") from e
    creds = Credentials.from_authorized_user_info(json.loads(raw), list(SCOPES))  # type: ignore[no-untyped-call]
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise GoogleError("the Google token was refused, run `hirelane google connect` again. "
                              "If your OAuth app is still in testing mode, tokens expire after 7 days.") from e
        secrets.set_secret(secrets.GOOGLE_TOKEN, creds.to_json())
    return creds


def service(name: str, version: str) -> Any:
    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        raise GoogleError("install the google extra: pip install 'hirelane[google]'") from e
    return build(name, version, credentials=credentials(), cache_discovery=False)
