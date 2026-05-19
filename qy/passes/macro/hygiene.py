# coding: utf-8
"""macro.hygiene pass。.

目标：
- 执行 macro hygiene、gensym、capture 规则。
- 保证 expansion 后的 symbol identity 可追踪。

当前：
- 占位 pass；实现仍分散在 macro hygiene/scope/trace 模块。
"""
