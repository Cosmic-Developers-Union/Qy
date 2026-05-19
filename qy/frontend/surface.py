# coding: utf-8
"""Surface dialect 实现目标模块。

目标：
- 实现默认 surface dialect 的 sugar rewrite。
- 只做静态可描述的 spelling rewrite：
  - 'x -> (quote x)
  - `x -> (quasiquote x)
  - ,x -> (unquote x)
  - ,@x -> (unquote-splicing x)

当前：
- 占位模块；当前实现可能嵌入在 reader.py 中。

禁止：
- 不得实现 unrestricted reader macro。
- 不得引入 runtime evaluation。
"""

from __future__ import annotations

# TODO: Phase B 中实现 surface dialect