# coding: utf-8
"""resolve.spaces pass。.

目标：
- 执行符号提升、symbol-space layout、binding slot 分配。
- 处理 define-once、shadow、pending binding、meta-space。

当前：
- 占位 pass（HIR 层尚未实现独立 layout 事实）。
- 低层 symbol-space / binding-slot layout 已在 LIR abstract-machine dialect
  落地：`qy/passes/lir/spaces.py` 把 `ENTER_SCOPE` / `DEFINE_ONCE` 降成
  `SS_ENTER` / `SS_LEAVE` / `SLOT_COMPLETE` 并产出 `LIRSymbolSpaceLayout`，
  使 L8/L9 verifier 生效。
- 仍待推进：HIR → MIR 携带稳定 binding id / slot，使 `resolve.spaces` 成为
  真正的 HIR 层 pass，而不是在 LIR 从指令流重建。

重要性：
- 这是 Qy 最关键 pass 之一，语言复杂度首先在这里显式化。
"""
