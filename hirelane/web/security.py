"""Access control for the web interface.

By default the server listens on loopback only. If a token is stored in the keyring, every page requires a signed
session cookie obtained by presenting that token. Binding to another address without a token is refused.
"""
from __future__ import annotations

import hmac
import ipaddress
from urllib.parse import urlsplit

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from .. import secrets

COOKIE = "af_session"
SESSION_MAX_AGE_S = 60 * 60 * 24 * 14
SESSION_VALUE = b"ok"
LOOPBACK_NAMES = {"localhost"}


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_bind(host: str) -> None:
    """Refuse to expose the interface beyond this machine without a token."""
    if not is_loopback(host) and not secrets.get_secret(secrets.WEB_TOKEN):
        raise RuntimeError("refusing to listen on a non-loopback address without a token, "
                           "run `hirelane set-key web-token` first")


def _signer() -> TimestampSigner:
    token = secrets.get_secret(secrets.WEB_TOKEN) or ""
    return TimestampSigner(token + "|hirelane-session")


def auth_required() -> bool:
    return bool(secrets.get_secret(secrets.WEB_TOKEN))


def token_matches(candidate: str) -> bool:
    token = secrets.get_secret(secrets.WEB_TOKEN) or ""
    return bool(token) and hmac.compare_digest(candidate.encode(), token.encode())


def issue_cookie() -> str:
    return _signer().sign(SESSION_VALUE).decode()


def cookie_valid(value: str | None) -> bool:
    if not value or not auth_required():
        return not auth_required()
    try:
        return _signer().unsign(value, max_age=SESSION_MAX_AGE_S) == SESSION_VALUE
    except (BadSignature, SignatureExpired):
        return False


def same_origin(origin: str | None, host: str | None) -> bool:
    """A browser form post carries an Origin header. It must name this server."""
    if not origin:
        return True               # non-browser clients and same-site navigations may omit it
    return bool(host) and urlsplit(origin).netloc == host
