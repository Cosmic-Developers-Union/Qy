# coding: utf-8
"""lir.lower pass。.

目标：
- 将 MIR 降到 LIR。
- 执行 instruction selection、layout、ABI、slot/frame 低层显式化。

当前：
- 占位 pass；旧实现仍在 `qy/passes/lower_lir.py` 与 `qy/lir_lowering.py`。
"""
