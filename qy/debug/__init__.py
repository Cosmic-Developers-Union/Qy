# coding: utf-8
"""调试与 trace 目标包。.

目标：
- 承载 IR dump、macro trace、VM debug、LLVM command log、pipeline trace。
- 为 CLI、LSP、测试快照提供统一 debug 输出。

当前：
- 占位包；现有 debug 能力分散在 dump 函数、VM debug、macro trace 中。

禁止：
- debug 输出不得修正程序语义。
"""
