# coding: utf-8
"""静态检查工具。.

目标：承载 analyzer / static check 能力。
当前：从 qy.analyzer 迁移中，保留 re-export 兼容。
禁止：不得承载 runtime 执行语义。
"""

from __future__ import annotations

from qy.analyzer import Analysis
from qy.analyzer import Diagnostic
from qy.analyzer import analyze
from qy.analyzer import analyze_source

__all__ = ["Analysis", "Diagnostic", "analyze", "analyze_source"]
