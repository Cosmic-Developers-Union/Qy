# coding: utf-8
"""Pass 基础接口目标模块。

目标：
- 定义 Pass、PassContext、PassResult、PassId、PassArtifact 等公共结构。
- 让每个 pass 明确输入 artifact、输出 artifact、诊断与 dump 名称。

当前：
- 占位模块；旧 lowering 仍在 `qy/passes/lower_hir.py`、`lower_mir.py`、`lower_lir.py`。

禁止：
- 不得在基础接口中实现具体语言变换。
"""

