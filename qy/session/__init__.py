# coding: utf-8
"""编译会话目标包。

目标：
- 承载单次编译/执行会话的配置、feature flags、profile、source manager、diagnostic reporter。
- 让 reader、analysis、passes、runtime 共享同一实例事实。

当前：
- 占位包；相关事实仍分散在 `Qy`、Environment、CLI 参数中。

禁止：
- 不得成为全局单例状态。
"""

