# Qy

Qy 是一个由 Python 实现的符号化 Lisp 方言，核心是代数效应 + 寄存器虚拟机。Python 是宿主，不是语言语义本体。

## 编译管线

语言契约围绕单一路径展开：

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

规范入口：

- **源码 → bytecode（单次）**：`qy.build.pipeline.compile_source_to_bytecode`
  —— 这是唯一允许的端到端路径。
- **按阶段产物**：`compile_source_to_kind(source, kind)`，
  其中 `kind ∈ {"core-ast", "hir", "mir", "lir", "bytecode"}`。
- **CLI 调试**：`qy ast`、`qy expand`、`qy hir`、`qy mir`、`qy lir`、
  `qy bytecode`、`qy run`。
- **公共 API**：`Qy` / `AsyncQy`（`qy.runtime`）用于完整求值；
  `RegisterVirtualMachine`（`qy.vm.instance.machine`）用于 bytecode 执行。

`Qy.evaluate_source(...)` 仍是完整求值的标准便利入口。backend 选择**不是**模型的一部分：register VM 是唯一执行目标。

已移除的单阶段入口：`Qy.macroexpand_source`、`Qy.lower`、`Qy.lower_mir`、
`Qy.compile_bytecode`、`Qy.evaluate_bytecode`、`Qy.evaluate_ir`、
`Qy.evaluate_ir_source`、`qy.ir_vm.*`、`qy.evaluator`、
`Qy(backend=...)`。详见 `docs/pipeline.md` §"稳定 API 与删除对象"。

Macro 展开默认通过 `MacroExpansionOptions(effect_policy="deny")` 拒绝
compile-time effect，避免在未显式授权的情况下执行不透明的编译期副作用。

当前核心保持很小：

- reader：qy 源码 → 符号表达式（`qy.frontend.reader`）
- surface dialect：`'x`、`quasiquote` 内 `,x` 等确定性拼写规约（`qy.frontend.surface`）
- CST 解析器：保留 trivia 的具体语法树（`qy.frontend.cst`）
- HIR / MIR / LIR / bytecode：相互独立的管线阶段（`qy.ir.*`、`qy.backend.vm.*`）
- analyzer：诊断和轻量类型检查（`qy.analysis`）
- formatter：锁定风格的 qy 源码格式化（`qy.tools.fmt`）
- CLI：AST、macro 展开、HIR、MIR、LIR、bytecode 和执行视图（`qy.cli`）
- LSP：基于 pygls 的诊断、补全、hover 和格式化（`qy.tools.lsp`）

## 使用

求值文件（推荐显式子命令形式；`qy FILE` 是等价快捷方式，实现在 `qy/cli/_app.py`）：

```shell
qy run examples/validation/00_host_arithmetic.qy
uv run python examples/run_validation.py
```

启动交互式解释器：

```shell
qy repl
```

通过 stdio 启动语言服务器：

```shell
qy lsp
```

格式化、查看 AST、类型检查：

```shell
qy fmt examples/validation/00_host_arithmetic.qy
qy ast examples/validation/00_host_arithmetic.qy
qy check examples/validation/00_host_arithmetic.qy
```

Python API：

```python
from qy import Qy

qy = Qy()
assert qy.evaluate_source("(+ 1 2)") == 3
```

通过规范管线编译：

```python
from qy import Qy
from qy.build.pipeline import compile_source_to_bytecode

qy = Qy()
result = compile_source_to_bytecode("(+ 1 2)", qy.session)
assert result.ok
```

嵌入式使用并注册应用算子：

```python
from qy import Qy
from qy import PureOperator
from qy import Symbol
from qy.std import StandardModule
from qy.std import register_module

qy = Qy()

@qy.register_pure("double")
def double(value):
    return value * 2

assert qy.evaluate_source("(double 21)") == 42

register_module(
    StandardModule(
        "app.math",
        {Symbol("triple"): PureOperator("triple", lambda x: x * 3)},
    )
)
qy.evaluate_source("(from app.math import triple as t)")
assert qy.evaluate_source("(t 14)") == 42
```

## 算子类型

Qy 使用算子元数据描述求值行为。最小核心围绕 syntax、chain、binding、
control、ordering/join、function、macro、effect 和 module 形式；其余
能力放在 stdlib 或显式 host 注入命名空间中。五种 legacy operator
dispatch 类（`PureOperator` / `ScopeOperator` / `ControlOperator` /
`EffectOperator` / `MetaOperator`）仍为向后兼容而保留，**但不再是主要
扩展路径**——新增核心语义必须到达 MIR / LIR / bytecode / VM，而不是
这套 legacy dispatch。

示例：

```lisp
(defun square (x)
  (* x x))

(square 12)
```