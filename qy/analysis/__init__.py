# coding: utf-8
"""静态分析目标包。

目标：
- 承载作用域、引用、逃逸、活跃变量、effect analysis、类型/签名检查。
- 读取 session/project/profile/operator metadata 的统一事实。

当前：
- 占位包；现有分析实现仍在 `qy/analyzer.py`。

禁止：
- 不得执行 runtime evaluation。
"""

