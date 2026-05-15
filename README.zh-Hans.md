# Qy

Qy 是一个由 Python 实现的符号化 Lisp 方言。

## 编译管线

语言契约围绕单一路径展开：

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

对应的 Python API 入口是 `Qy.read(...)`、`Qy.macroexpand_source(...)`、`Qy.lower(...)`、`Qy.lower_mir(...)`、`Qy.compile_bytecode(...)` 和 `RegisterVirtualMachine(...)`。

`Qy.evaluate_source(...)` 仍然保留为兼容性便利入口，但执行目标是 register VM，backend 选择不再是模型的一部分。

Macro expansion 默认通过 `MacroExpansionOptions(effect_policy="deny")` 拒绝 compile-time effect，避免在未显式授权的情况下执行不透明的编译期副作用。

当前核心保持很小：

- reader：qy 源码 -> 符号表达式
- tuple exchange：使用显式 `Symbol(...)` 的 Python tuple 交换格式
- analyzer：诊断和轻量类型检查
- surface dialect：如 `'x` 和 quasiquote 内 `,x` 的确定性拼写规约
- formatter：锁定风格的 qy 源码格式化
- CLI：AST、macro 展开、HIR、MIR、LIR、bytecode 和执行视图
- LSP：基于 pygls 的诊断、补全、hover 和格式化

## 使用

求值文件：

```shell
qy examples/validation/00_host_arithmetic.qy
uv run python examples/run_validation.py
```

启动交互式解释器：

```shell
qy
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
from qy import Symbol
from qy import evaluate
from qy import evaluate_source

assert evaluate_source("(+ 1 2)") == 3
assert evaluate((Symbol("+"), 1, 2)) == 3
```

在 Python tuple 表达式中，普通 Python 值都是字面量。只有显式使用 `Symbol(...)` 才表示 qy 符号。

```python
from qy import Symbol
from qy import evaluate

evaluate((Symbol("+"), 1, 2))  # 3
evaluate(("+", 1, 2))          # error: "+" 是 Python 字符串字面量
```

显式运行整条管线：

```python
from qy import Qy

qy = Qy()
expansion = qy.macroexpand_source("(+ 1 2)")
program = qy.lower(expansion.forms)
mir = qy.lower_mir(program)
bytecode = qy.compile_bytecode(program)

assert mir.ok
assert qy.evaluate_bytecode(bytecode) == 3
```

嵌入式使用并注册应用算子：

```python
from qy import Qy

qy = Qy()

@qy.register_pure("double")
def double(value):
    return value * 2

assert qy.evaluate_source("(double 21)") == 42
```

## 算子类型

Qy 使用算子元数据描述求值行为。最小核心围绕 syntax、chain、binding、control、ordering/join、function、macro、effect 和 module 形式；其余能力放在 stdlib 或显式 host 注入命名空间中。

示例：

```lisp
(defun square (x)
  (* x x))

(square 12)
```
