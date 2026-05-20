# coding: utf-8
"""VM 并发调度器。.

目标：管理 parallel/all/race 的任务调度与 barrier continuation。
当前：目标结构定义，实际调度仍在 register_vm.py。
禁止：不得定义 effect 协议规格。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class ScheduledTask:
    """一个被调度的并发任务。."""

    thunk_index: int
    state: TaskState = TaskState.PENDING
    result: object = None
    error: BaseException | None = None
