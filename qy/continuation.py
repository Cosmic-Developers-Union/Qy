# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/backend/vm/spec/effect.py + qy/vm/instance/frame.py

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field

from qy.errors import QyEffectError

__all__ = ["QyContinuation"]


async def _await_if_needed(value: object) -> object:
    if inspect.iscoroutine(value):
        return await value
    return value


@dataclass(slots=True)
class QyContinuation:
    effect: str
    resumable: bool
    _resume: Callable[[object], object]
    _consumed: bool = field(default=False, init=False)

    async def resume(self, value: object) -> object:
        if not self.resumable:
            raise QyEffectError(
                f"effect {self.effect!r} is not resumable",
                metadata={"effect": self.effect, "value": value},
            )
        if self._consumed:
            raise QyEffectError(
                f"continuation for effect {self.effect!r} has already been resumed (one-shot)",
                metadata={"effect": self.effect},
            )
        self._consumed = True
        return await _await_if_needed(self._resume(value))
