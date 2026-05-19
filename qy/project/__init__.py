# coding: utf-8
"""项目与包管理目标包。

目标：
- 承载 `qy.toml`、package、module root、依赖解析、项目级 profile 配置。
- 为 import resolver、build graph、LSP workspace 提供同一项目模型。

当前：
- 占位包；现有模块路径逻辑仍分散在 source module/import 相关实现中。

禁止：
- 不得执行 source lowering 或 VM 运行。
"""

