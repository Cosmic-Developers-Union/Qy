# coding: utf-8
"""源码区间与位置模型。.

提供 SourceSpan 数据类和 get_span 工具函数，作为 reader、diagnostics、IR、debug 的统一 span 来源。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

__all__ = ["SourceSpan", "get_span"]


@dataclass(frozen=True, slots=True)
class SourceSpan:
    source: str | None = None
    start_line: int | None = None
    start_column: int | None = None
    end_line: int | None = None
    end_column: int | None = None

    @property
    def line(self) -> int | None:
        return self.start_line

    @property
    def column(self) -> int | None:
        return self.start_column

    def format(self) -> str:
        location = self.source or "<source>"
        if self.start_line is None or self.start_column is None:
            return location
        return f"{location}:{self.start_line}:{self.start_column}"


def get_span(value: object) -> SourceSpan | None:
    """从 form 中提取 SourceSpan，支持 Symbol、Chain 与带 span 属性的对象。."""
    from qy.core.syntax import Chain

    # 避免循环导入：Symbol 在 reader 中定义
    if hasattr(value, "span") and not isinstance(value, Chain):
        return cast("SourceSpan | None", value.span)
    if isinstance(value, Chain):
        return cast("SourceSpan | None", value.span)
    return None
