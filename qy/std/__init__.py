# coding: utf-8
"""标准库：standard profile 与标准库目标包。.

目标：
- 提供 standard profile 与标准库实现
- 包含常用算子（+、-、*、/ 等）和标准函数
- 定义默认的 pre-symbol-space-chain

当前：
- 占位包，qy/stdlib 是迁移期兼容目录
- 新增长期标准能力应进入此包

禁止：
- 不是 Python helper 的随机集合
- 不得将 profile 便利算子提升为核心 form
- 不得绕过 symbol-space-chain 机制
"""
