from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine on its own thread and loop.

    The Playwright sync API keeps an event loop running on the main thread for the whole session, which makes a plain
    asyncio.run raise in tests that run after a browser test.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
