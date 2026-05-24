# coding: utf-8
"""Async utilities for QyLang.

This module provides utilities for working with async/await in QyLang,
particularly for bridging sync and async code.
"""

from __future__ import annotations

import asyncio


def run_coro(coro):
    """Run a coroutine in a sync context.

    If there's already a running event loop, creates a new thread with a new loop.
    Otherwise, uses asyncio.run().

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


__all__ = ["run_coro"]
