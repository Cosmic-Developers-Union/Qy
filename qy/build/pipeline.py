# coding: utf-8
"""Pipeline driver 目标模块。.

目标：
- 串联 source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode。
- 只编排阶段，不在这里实现阶段语义。

当前：
- 占位模块；实际编排仍主要位于 `Qy` runtime 和 CLI。
"""
