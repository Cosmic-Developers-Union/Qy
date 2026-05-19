# coding: utf-8
"""源码与位置映射目标包。

目标：
- 承载 SourceFile、Span、SourceMap、line/column 映射。
- 让 reader、macro、IR dump、diagnostics、debug 使用同一位置模型。

当前：
- 占位包；SourceSpan 仍位于 `qy/errors.py`，reader 也有自己的 span 表达。

禁止：
- 不得放入 project/module loader 逻辑。
"""

