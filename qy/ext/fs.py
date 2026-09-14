# coding: utf-8
"""``qy.ext.fs``：文件系统宿主扩展。.

语言侧通过 ``(from qy.ext.fs import read-file)`` 引入；扩展声明所需的
``filesystem`` capability。宿主对象/错误在边界上转换为语言级错误，
不把 Python 异常类型暴露给语言。
"""

from __future__ import annotations

from pathlib import Path

from qy.core.operator_signature import Arity
from qy.core.operator_signature import OperatorSignature
from qy.core.operators import EffectOperator
from qy.errors import EvaluationError
from qy.ext.descriptor import ExtensionBinding
from qy.ext.descriptor import ExtensionCapability
from qy.ext.descriptor import ExtensionDescriptor
from qy.ext.registry import register_extension
from qy.frontend.reader import Symbol
from qy.import_.module import StandardModule
from qy.sem.core import StringValue
from qy.session.runtime_space import RuntimeSpace as Environment

__all__ = ["DESCRIPTOR", "module"]


async def _read_file(args: tuple[object, ...], env: Environment) -> object:
    del env
    if len(args) != 1:
        raise EvaluationError("read-file expects exactly one path argument")
    path_value = args[0]
    if isinstance(path_value, StringValue):
        path_text = path_value.value
    elif isinstance(path_value, Symbol):
        path_text = path_value.name
    elif isinstance(path_value, str):
        path_text = path_value
    else:
        raise EvaluationError(f"read-file: expected a path string, got {type(path_value).__name__}")
    try:
        return StringValue(Path(path_text).read_text(encoding="utf-8"))
    except OSError as e:
        raise EvaluationError(f"read-file: cannot read {path_text!r}: {e}") from e


_READ_FILE_SIGNATURE = OperatorSignature("string", Arity(1, 1))


def module() -> StandardModule:
    """``qy.ext.fs`` 模块：文件系统扩展。."""
    return StandardModule(
        "qy.ext.fs",
        {
            Symbol("read-file"): EffectOperator(
                "read-file",
                _read_file,
                "读取文本文件内容并返回 string；参数为路径。",
                signature=_READ_FILE_SIGNATURE,
            ),
        },
    )


DESCRIPTOR = ExtensionDescriptor(
    name="qy.ext.fs",
    module_name="qy.ext.fs",
    version="0.1",
    description="文件系统宿主扩展。",
    capabilities=(ExtensionCapability("filesystem", "读取宿主文件系统"),),
    bindings=(
        ExtensionBinding(
            "read-file",
            kind="effect",
            doc="读取文本文件内容并返回 string。",
            signature=_READ_FILE_SIGNATURE,
            capabilities=("filesystem",),
        ),
    ),
)

register_extension(DESCRIPTOR, module)
