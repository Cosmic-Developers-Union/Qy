# coding: utf-8
"""静态检查工具。.

目标：承载 analyzer / static check 能力。
禁止：不得承载 runtime 执行语义。
"""

from __future__ import annotations

from qy.analysis import Analysis
from qy.analysis import Diagnostic
from qy.analysis import analyze
from qy.analysis import analyze_source

__all__ = ["Analysis", "Diagnostic", "analyze", "analyze_source"]
