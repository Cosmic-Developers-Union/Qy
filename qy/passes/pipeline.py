# coding: utf-8
"""Pass pipeline 调度器。.

目标：
- 按固定阶段顺序调度 pass。
- 支持按 pass id dump 中间结果，例如 `--after=effect.flatten`。
- 支持按目标 artifact 停止，例如 `--target=lir`。

当前：
- 占位模块。

禁止：
- 调度器不得实现具体 pass 语义。
"""

from __future__ import annotations

from typing import Optional

from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult


class Pipeline:
    """Pass 调度器。.

    职责：
    - 按顺序执行 pass
    - 在指定 pass 后 dump artifact
    - 运行到目标 artifact 后停止
    """

    def __init__(self):
        """初始化 pipeline。."""
        self.passes: list[Pass] = []

    def add_pass(self, pass_: Pass) -> None:
        """添加 pass 到 pipeline。.

        Args:
            pass_: 要添加的 pass
        """
        self.passes.append(pass_)

    def run(
        self,
        context: PassContext,
        after: Optional[str] = None,
        target: Optional[str] = None,
    ) -> PassResult:
        """运行 pipeline。.

        Args:
            context: Pass 上下文，包含初始输入
            after: 在此 pass 后 dump artifact（pass name）
            target: 运行到此 pass 后停止（pass name）

        Returns:
            最终 PassResult

        示例：
            >>> pipeline = Pipeline()
            >>> pipeline.add_pass(LowerHIRPass())
            >>> pipeline.add_pass(LowerMIRPass())
            >>> result = pipeline.run(context, after="hir.lower")
        """
        current_artifact = context.input_artifact
        all_diagnostics = []

        for pass_ in self.passes:
            # 准备当前 pass 的上下文
            pass_context = PassContext(
                input_artifact=current_artifact,
                diagnostics=[],
                options=context.options,
            )

            # 执行 pass
            result = pass_.run(pass_context)

            # 收集诊断
            all_diagnostics.extend(result.diagnostics)

            # 如果失败，立即返回
            if not result.success:
                return PassResult(
                    success=False,
                    artifact=result.artifact,
                    diagnostics=all_diagnostics,
                )

            # 更新当前 artifact
            current_artifact = result.artifact

            # 如果指定了 --after，在此 pass 后 dump
            if after == pass_.name:
                # TODO: 实现 dump 逻辑（对接 qy/debug/）
                pass

            # 如果指定了 --target，在此 pass 后停止
            if target == pass_.name:
                return PassResult(
                    success=True,
                    artifact=current_artifact,
                    diagnostics=all_diagnostics,
                )

        # 所有 pass 执行完毕
        return PassResult(
            success=True,
            artifact=current_artifact,
            diagnostics=all_diagnostics,
        )
