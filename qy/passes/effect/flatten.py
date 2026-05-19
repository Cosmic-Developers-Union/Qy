# coding: utf-8
"""effect.flatten pass。.

目标：
- 将 continuation / handler / resume 降成 CFG/state 形式。
- 为 MIR 与 LIR 消除语言级 effect form 做准备。

当前：
- 占位 pass。

重要性：
- 这是从语言级 effect 到底层可执行控制流的关键转换。
"""
