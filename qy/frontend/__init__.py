# coding: utf-8
"""前端：源码到 raw AST 的转换。.

目标：
- 只负责读取 source、构造 raw AST、执行 default surface dialect
- raw AST 只能由 symbol 与不可变 chain 组成，带源码位置追踪
- 提供基于 Lark 的 S-expression 解析器

当前：
- 占位包，等待从 qy/reader.py 迁移

禁止：
- 不得提前创建 runtime value
- 不得在 reader 阶段引入语义解析
"""

from __future__ import annotations
