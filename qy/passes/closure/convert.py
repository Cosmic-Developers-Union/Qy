# coding: utf-8
"""closure.convert pass。.

目标：
- 将 lambda/defun 转换为 closure/env 模型。
- 显式化捕获、逃逸、slot copy policy。

当前：
- 占位 pass。

重要性：
- closure 与 symbol-space、continuation、effect 的边界在这里固定。
"""
