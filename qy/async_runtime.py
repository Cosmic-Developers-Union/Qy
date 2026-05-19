# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/vm/instance scheduler/async bridge

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Coroutine
from typing import cast

__all__ = ["run_async"]


def run_async(awaitable: object) -> object:
    if not inspect.isawaitable(awaitable):
        return awaitable
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(cast(Coroutine[object, object, object], awaitable))

    result: object = None
    error: BaseException | None = None

    def run_in_thread() -> None:
        nonlocal result, error
        try:
            result = asyncio.run(cast(Coroutine[object, object, object], awaitable))
        except BaseException as e:
            error = e

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    thread.join()
    if error is not None:
        raise error
    return result
