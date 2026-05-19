# coding: utf-8
"""resolve.spaces pass。

目标：
- 执行符号提升、symbol-space layout、binding slot 分配。
- 处理 define-once、shadow、pending binding、meta-space。

当前：
- 占位 pass。

重要性：
- 这是 Qy 最关键 pass 之一，语言复杂度首先在这里显式化。
"""

