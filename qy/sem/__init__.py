# coding: utf-8
"""语义模型：面向执行的值模型和抽象机语义。.

目标：
- 保存面向 libqy / VM / backend 的值模型
- 定义抽象机语义，包括 continuation、effect handler、symbol-space-chain
- 提供 runtime value 类型（EffectDefinition、BytecodeFunctionValue 等）

当前：
- core.py 定义 number / string / object family 值模型
- runtime.py 提供运行时值（EffectDefinition）
- host.py 提供 host reference 包装

边界：
- 语法 datum（symbol / chain）与 Qy 自身对象（nil / T / none）的真源是
  `qy.core.syntax`，本包不得重复定义
- 宿主值 ↔ Qy 语义值的转换属于 `qy.ext` 扩展边界，本包不提供桥接层

禁止：
- 不得反向依赖 parser、CLI 或 std
- 不得包含具体的 VM 实现细节
- 不得混入工具链逻辑
"""

from qy.sem.convert import from_qy_value
from qy.sem.convert import to_qy_value
from qy.sem.core import ArrayValue
from qy.sem.core import CharValue
from qy.sem.core import ComplexValue
from qy.sem.core import DictValue
from qy.sem.core import Float32Value
from qy.sem.core import FloatValue
from qy.sem.core import HashMapValue
from qy.sem.core import Int32Value
from qy.sem.core import Int64Value
from qy.sem.core import IntegerValue
from qy.sem.core import IntValue
from qy.sem.core import ListValue
from qy.sem.core import NumberValue
from qy.sem.core import ObjectValue
from qy.sem.core import RationalValue
from qy.sem.core import SetValue
from qy.sem.core import StringValue
from qy.sem.core import TupleValue
from qy.sem.core import Value
from qy.sem.runtime import EffectDefinition

__all__ = [
    "ArrayValue",
    "CharValue",
    "ComplexValue",
    "DictValue",
    "EffectDefinition",
    "Float32Value",
    "FloatValue",
    "HashMapValue",
    "Int32Value",
    "Int64Value",
    "IntValue",
    "IntegerValue",
    "ListValue",
    "NumberValue",
    "ObjectValue",
    "RationalValue",
    "SetValue",
    "StringValue",
    "TupleValue",
    "Value",
    "from_qy_value",
    "to_qy_value",
]
