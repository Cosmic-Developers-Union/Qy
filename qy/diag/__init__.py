# coding: utf-8
"""统一诊断系统目标包。

目标：
- 承载 error、warning、span、note、fixit、reporter 等诊断模型。
- 为 reader、macro、analysis、passes、CLI、LSP 提供统一诊断输出。

当前：
- 占位包；现有轻量诊断仍在 `qy/diagnostics.py`。

禁止：
- 不得承载语言级异常类；异常分类属于 `qy/errors`。
"""

