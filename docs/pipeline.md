# Qy Pipeline

本文档描述 Qy 唯一编译与执行管线。Qy 不保留可选 runtime backend；register VM 是唯一执行器。

## 管线概览

```text
source
  -> raw AST
  -> surface dialect
  -> macro expand
  -> HIR
  -> MIR
  -> LIR
  -> bytecode
  -> register VM
```

`Qy.evaluate_source(...)` 与 `Qy.evaluate_bytecode(...)` 是当前稳定执行入口，统一以 register VM 为执行目标。

## 分层边界

每层有且只有一个职责；禁止跨层解释语义。

| 层 | 输入 | 输出 | 产生 diagnostics | 是否依赖 Environment |
| --- | --- | --- | --- | --- |
| source | 文本文件 / stdin | 源码字符串 | 否 | 否 |
| ast / reader | 源码字符串 | raw syntax datum forest；每个 form 只能是 `symbol` 或不可变 `chain` | 是，reader syntax error | 否 |
| surface dialect | raw `list[Form]` | default-dialect `list[Form]`，如 `'x`、quasiquote 内 `,x` / `,@x` | 否 | 否 |
| expand / macroexpand | surface-dialect-expanded `list[Form]` | `MacroExpansion(forms, diagnostics, traces)` | 是，展开错误、compile-time effect 错误 | 是，compile-time facade 捕获环境快照 |
| HIR / lower | macroexpanded forms | `ProgramIR`（`CallExpr`、`LetExpr`、`HandleExpr`、`PipelineExpr` 等） | 是，未解析符号、arity、module import 等 | 是 |
| MIR / lower_mir | `ProgramIR` | `MIRProgram`（CFG + virtual register） | 是，覆盖不到的 HIR 节点进入 MIR diagnostics | 否 |
| LIR / lower_lir | `MIRProgram` | `LIRProgram`（线性化低层 IR，register layout、effect frame layout、host-call lowering） | 是 | 否 |
| bytecode | `LIRProgram` | `BytecodeProgram`（纯结构转换，不重新理解语义） | 是，沿用 LIR diagnostics | 否 |
| register VM | `BytecodeProgram` | 运行结果 / top-level 结果列表 | 运行期异常 | 是，执行时需要 runtime environment |

**跨层禁止规则**：

- reader 只负责源码到 `symbol` / `chain`；不得把 number、string 或其他 runtime value 提前塞进 raw AST。
- bytecode compiler 不能重新理解 HIR/MIR 语义；语义 lowering 必须经由 LIR。
- MIR lowering 不能访问 Environment（不能查 runtime binding）。
- HIR 之上（reader/surface dialect/macroexpand）不得引入 bytecode/VM 特定的 representation。

## 稳定 API 与删除对象

推荐稳定入口：

- `Qy.read`
- `Qy.macroexpand` / `Qy.macroexpand_source`
- `Qy.lower` / `Qy.lower_source`
- `Qy.lower_mir`
- `Qy.compile_bytecode`
- `Qy.evaluate_source` / `Qy.evaluate_bytecode`
- `lower_lir`
- `RegisterVirtualMachine`

已删除对象（禁止回归）：

- `Qy.evaluate_ir` / `Qy.evaluate_ir_source`
- `qy.ir_vm/` 目录与 `qy.ir_vm.*` public execution API
- `Qy(backend=...)` 与 `EvaluationBackend`
- 直接从 `qy.evaluator` 引入运行时类型或 legacy evaluator helper

## CLI 调试命令

每个命令对应管线的一个阶段产物，不执行 runtime side effect（除非命令说明需要 compile-time macro 求值）。

```shell
# 观察 reader 输出 syntax datum
qy ast FILE

# 观察 macro 展开后 syntax datum
qy expand FILE

# 观察 HIR dump
qy hir FILE

# 观察 MIR CFG dump
qy mir FILE

# 观察 LIR 线性化 dump
qy lir FILE

# 观察 bytecode dump
qy bytecode FILE

# 默认执行（register VM）
qy run FILE
qy FILE   # 等价 run 快捷方式
```

所有命令都支持 stdin（用 `-` 代替文件路径）：

```shell
cat examples/hello.qy | qy mir -
printf '(+ 1 2)\n' | qy bytecode -
```

约定：

- 正常产物输出到 stdout。
- diagnostics 输出到 stderr。
- 若任何阶段产生 error 级 diagnostics，命令以退出码 `1` 返回。
- `mir`、`lir`、`bytecode` 输出会保留 `SourceSpan`，便于 review 时回到源码位置。

## Compile-Time Runtime 现状

macro body 的 compile-time facade 仍然是过渡实现，但已经不再把 evaluator 当作主执行面：

- macro 定义捕获的是 compile-time environment facade，不直接依赖 `Environment` 类型。
- compile-time 可用 binding 当前等于定义时环境中的现有 binding 快照，加上展开期注入的 `gensym` 与 `capture`。
- compile-time effect 受 `effect_policy` 控制；macro body 失败统一包装成 `failed during compile-time evaluation` diagnostics。

这仍是过渡实现，compile-time/runtime 能力未完全隔离，但边界已比直接暴露 evaluator 类型更清晰。

## Macro Hygiene 现状

当前 macroexpand 实现最小 hygiene：

- macro 引入的局部 binder（`let` binding、`lambda` / `defun` params、`handle` params）展开后自动 rewrite 为稳定 hidden symbol，避免捕获调用点同名 symbol。
- macro 引入的自由 symbol 默认按定义点绑定解析。
- 需要显式捕获调用点 binding 时，使用 `(capture form)`：
  - 默认 hygiene：`(cons '+ ...)` 固定到 macro 定义点的 `+`。
  - 显式捕获：`(cons (capture '+) ...)` 保留调用点的 `+`。

`MacroExpansionTrace.renames` 与 `MacroExpansion.source_map[*].renames` 暴露这些 rewrite，供 diagnostics / LSP 消费。
