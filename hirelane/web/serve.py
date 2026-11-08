"""Start the web interface."""
from __future__ import annotations

from ..config import Paths, get_paths, load_settings
from . import security
from .app import create_app

LOOPBACK = "127.0.0.1"


def serve(host: str = LOOPBACK, port: int | None = None, paths: Paths | None = None) -> None:
    import uvicorn

    p = paths or get_paths().ensure()
    security.check_bind(host)
    chosen = port or load_settings(p.settings_file).web_port
    uvicorn.run(create_app(p), host=host, port=chosen, log_level="warning")
