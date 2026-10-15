"""Secrets live in the operating system keyring and never in a config file, the database or a log.

The service name is fixed so hirelane can never read or overwrite another program's entries.
"""
from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from .config import KEYRING_SERVICE

AI_KEY = "ai-api-key"
WEB_TOKEN = "web-token"
GOOGLE_TOKEN = "google-token"
GOOGLE_CLIENT = "google-client"
ENV_PREFIX = "HIRELANE_SECRET_"
KNOWN_NAMES = (AI_KEY, WEB_TOKEN, GOOGLE_TOKEN, GOOGLE_CLIENT)


class SecretsError(RuntimeError):
    pass


def env_name(name: str) -> str:
    return ENV_PREFIX + name.upper().replace("-", "_")


def get_secret(name: str) -> str | None:
    """The secret from the keyring. An environment variable, for containers without a keyring, takes priority."""
    from_env = os.environ.get(env_name(name))
    if from_env:
        return from_env
    try:
        return keyring.get_password(KEYRING_SERVICE, name)
    except KeyringError as e:
        raise SecretsError(f"the keyring is not available: {e}") from e


def set_secret(name: str, value: str) -> None:
    if not value:
        raise SecretsError("refusing to store an empty secret")
    try:
        keyring.set_password(KEYRING_SERVICE, name, value)
    except KeyringError as e:
        raise SecretsError(f"the keyring is not available: {e}") from e


def delete_secret(name: str) -> bool:
    try:
        keyring.delete_password(KEYRING_SERVICE, name)
        return True
    except PasswordDeleteError:
        return False
    except KeyringError as e:
        raise SecretsError(f"the keyring is not available: {e}") from e


def describe() -> dict[str, bool]:
    """Which known secrets are set. Values are never returned."""
    return {name: bool(get_secret(name)) for name in KNOWN_NAMES}
