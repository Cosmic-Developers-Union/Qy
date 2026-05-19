# coding: utf-8
"""Pass 基础接口。.

目标：
- 定义 Pass、PassContext、PassResult、PassId、PassArtifact 等公共结构。
- 让每个 pass 明确输入 artifact、输出 artifact、诊断与 dump 名称。

当前：
- 占位模块；旧 lowering 仍在 `qy/passes/lower_hir.py`、`lower_mir.py`、`lower_lir.py`。

禁止：
- 不得在基础接口中实现具体语言变换。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Optional


@dataclass
class PassContext:
    """Pass 执行上下文。.

    包含：
    - 输入 artifact
    - 编译会话信息（诊断、符号表等）
    - 配置选项
    """

    # 输入 artifact（由上一个 pass 产生）
    input_artifact: Optional[Any] = None

    # 诊断收集器（TODO: 对接 qy/diag/）
    diagnostics: list = field(default_factory=list)

    # 配置选项（TODO: 对接 qy/session/）
    options: dict = field(default_factory=dict)


@dataclass
class PassResult:
    """Pass 执行结果。.

    包含：
    - 是否成功
    - 输出 artifact
    - 诊断信息
    """

    success: bool
    artifact: Optional[Any] = None
    diagnostics: list = field(default_factory=list)


class Pass:
    """Pass 基类。.

    每个 pass 必须：
    - 有唯一的 name（用于 --after=<name> dump）
    - 实现 run 方法
    - 明确输入/输出 artifact 类型（通过文档或类型注解）
    """

    def __init__(self, name: str):
        """初始化 pass。.

        Args:
            name: Pass 唯一标识符，例如 "hir.lower"、"effect.flatten"
        """
        self.name = name

    def run(self, context: PassContext) -> PassResult:
        """执行 pass。.

        Args:
            context: Pass 上下文，包含输入 artifact 和配置

        Returns:
            PassResult，包含输出 artifact 和诊断信息
        """
        raise NotImplementedError(f"Pass {self.name} 未实现 run 方法")
