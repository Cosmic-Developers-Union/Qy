# coding: utf-8
"""Reader 实现目标模块。

目标：
- 实现 source -> raw AST 的解析。
- 基于 Lark 的 S-expression 解析器。
- raw AST 只能由 symbol 和 immutable chain 组成。

当前：
- 实现位于 `qy/reader.py`。
- raw AST 仍在从 Python tuple 向目标模型迁移。

禁止：
- 不得提前将 literal (number/string) 物化为 Python 值。
- 不得在这里实现 runtime value。
"""

from __future__ import annotations

# 实现暂时保留在 qy/reader.py，参考 todo.md Phase B 进行迁移
# TODO: Phase B 中将实现迁移到本模块