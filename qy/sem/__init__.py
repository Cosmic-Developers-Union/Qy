# coding: utf-8
"""语义模型：面向执行的值模型和抽象机语义。.

目标：
- 保存面向 libqy / VM / backend 的值模型
- 定义抽象机语义，包括 continuation、effect handler、symbol-space-chain
- 提供 runtime value 类型（UserFunction、EffectDefinition、ComponentOperator 等）

当前：
- core.py 已定义完整 value hierarchy
- runtime.py 提供运行时值（UserFunction、EffectDefinition、ComponentOperator）
- bridge.py 提供迁移期转换

禁止：
- 不得反向依赖 parser、CLI 或 std
- 不得包含具体的 VM 实现细节
- 不得混入工具链逻辑
"""

from qy.sem.core import NIL
from qy.sem.core import ArrayValue
from qy.sem.core import ChainValue
from qy.sem.core import CharValue
from qy.sem.core import ComplexValue
from qy.sem.core import DatumValue
from qy.sem.core import Float32Value
from qy.sem.core import FloatValue
from qy.sem.core import HashMapValue
from qy.sem.core import Int32Value
from qy.sem.core import Int64Value
from qy.sem.core import IntegerValue
from qy.sem.core import IntValue
from qy.sem.core import NilValue
from qy.sem.core import NumberValue
from qy.sem.core import ObjectValue
from qy.sem.core import RationalValue
from qy.sem.core import StringValue
from qy.sem.core import SymbolValue
from qy.sem.core import T
from qy.sem.core import TValue
from qy.sem.core import Value
from qy.sem.runtime import ComponentOperator
from qy.sem.runtime import EffectDefinition
from qy.sem.runtime import UserFunction

__all__ = [
    "NIL",
    "ArrayValue",
    "ChainValue",
    "CharValue",
    "ComplexValue",
    "ComponentOperator",
    "DatumValue",
    "EffectDefinition",
    "Float32Value",
    "FloatValue",
    "HashMapValue",
    "Int32Value",
    "Int64Value",
    "IntValue",
    "IntegerValue",
    "NilValue",
    "NumberValue",
    "ObjectValue",
    "RationalValue",
    "StringValue",
    "SymbolValue",
    "T",
    "TValue",
    "UserFunction",
    "Value",
]
