# coding: utf-8
"""源码与位置映射包。.

承载 SourceFile、Span、SourceMap、line/column 映射。
让 reader、macro、IR dump、diagnostics、debug 使用同一位置模型。

禁止：
- 不得放入 project/module loader 逻辑。
"""

from qy.source.span import SourceSpan
from qy.source.span import get_span

__all__ = ["SourceSpan", "get_span"]
