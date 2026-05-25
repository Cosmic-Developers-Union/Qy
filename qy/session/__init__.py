# coding: utf-8
"""编译会话目标包。.

目标：
- 承载单次编译/执行会话的配置、feature flags、profile、source manager、diagnostic reporter。
- 让 reader、analysis、passes、runtime 共享同一实例事实。

当前：
- 占位包；相关事实仍分散在 `Qy`、Environment、CLI 参数中。

禁止：
- 不得成为全局单例状态。
"""

from qy.session.profile import LiteralResolver
from qy.session.profile import ProfileConfig
from qy.session.runtime_space import Environment
from qy.session.runtime_space import RuntimeSpace
from qy.session.runtime_space import create_standard_runtime_space
from qy.session.runtime_space import standard_environment

__all__ = [
    "Environment",
    "LiteralResolver",
    "ProfileConfig",
    "RuntimeSpace",
    "create_standard_runtime_space",
    "standard_environment",
]
