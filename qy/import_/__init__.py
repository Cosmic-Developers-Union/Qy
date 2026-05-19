# coding: utf-8
"""导入解析目标包。.

目标：
- 承载 module loader、import resolver、from/fold 与 package dependency 的连接层。
- 使用尾随下划线避免与 Python 关键字 `import` 冲突。

当前：
- 占位包；现有实现仍分散在 `source_modules.py` 与 std/imports 相关模块。

禁止：
- 不得直接实现 module body 求值；求值仍由 pipeline/VM 承担。
"""
