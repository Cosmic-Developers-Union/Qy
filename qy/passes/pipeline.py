# coding: utf-8
"""Pass pipeline 调度器目标模块。

目标：
- 按固定阶段顺序调度 pass。
- 支持按 pass id dump 中间结果，例如 `--after=effect.flatten`。
- 支持按目标 artifact 停止，例如 `--target=lir`。

当前：
- 占位模块。

禁止：
- 调度器不得实现具体 pass 语义。
"""

