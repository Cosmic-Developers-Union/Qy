# coding: utf-8
"""后端目标包：非核心验证/输出后端.

目标：
- 承载 LLVM backend、VM target 规格等非核心后端
- 不得引入第二 runtime backend

职责边界：
- backend/vm/: VM target 的规格、bytecode emit、验证与适配（不是 Python VM 实现）
- backend/llvm/: 可选的 LLVM 验证后端
"""

__all__ = []
