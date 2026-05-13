# Qy Pipeline

本文档描述当前公开的 Qy 编译与执行管线，以及哪些 API 属于稳定入口，哪些仍是兼容层。

## 管线概览

```text
source
  -> ast
  -> expand
  -> HIR
  -> MIR
  -> LIR
  -> bytecode
  -> register VM
```

`Qy.evaluate_source(...)` 默认仍使用 IR backend，因为它目前仍是语义最完整的参考实现。

`Qy(backend="bytecode")` 已可用，但 bytecode backend 仍是实验性后端：它适合 review、调试和核心 eager 子集验证，不应被当作完整语言执行器。

当前实现还没有独立 LIR dataclass/API；`compile_mir_bytecode` 暂时从 MIR 直接生成 bytecode。后续应补 LIR，禁止 bytecode compiler 重新理解 MIR 以上的语义。

## 分层边界

| 层 | 输入 | 输出 | 是否产生 diagnostics | 是否依赖 Environment |
| --- | --- | --- | --- | --- |
| source | 文本 | 源码字符串 | 否 | 否 |
| ast / reader | 源码字符串 | `list[Form]` syntax datum | 是，reader syntax error | 否 |
| expand / macroexpand | `list[Form]` | `MacroExpansion(forms, diagnostics, traces)` | 是，展开错误、compile-time effect 错误、compile-time evaluation 错误 | 是，当前通过 compile-time facade 捕获环境快照 |
| HIR / lower | macroexpanded form | `ProgramIR` | 是，未解析符号、arity、module import 等 | 是 |
| MIR / lower_mir | `ProgramIR` | `MIRProgram` | 是，当前覆盖不到的 HIR 节点应进入 MIR diagnostics | 否，消费的是已 lowering 的 HIR |
| LIR | `MIRProgram` | 待实现的低层 register VM IR | 是 | 否 |
| bytecode | LIR，当前暂时为 `MIRProgram` | `BytecodeProgram` | 是，沿用 MIR/LIR diagnostics | 否 |
| register VM | `BytecodeProgram` | 运行结果 / top-level 结果列表 | 运行期错误通过异常返回 | 是，执行时需要 runtime environment |

## 稳定 API 与兼容 API

推荐把下面这些入口当作当前稳定的 pipeline API：

- `Qy.read`
- `Qy.macroexpand` / `Qy.macroexpand_source`
- `Qy.lower` / `Qy.lower_source`
- `Qy.lower_mir`
- `Qy.compile_mir_bytecode`
- `Qy.compile_bytecode`
- `Qy.evaluate_ir` / `Qy.evaluate_bytecode`
- `compile_mir_bytecode`
- `compile_bytecode`
- `RegisterVirtualMachine`

下面这些 API 目前仍保留，但应视为 compatibility surface，而不是后续架构继续扩展的主入口：

- `qy.__init__` 中 re-export 的 `evaluate*`、`standard_environment`、`Environment`
- 直接从 `qy.evaluator` 引入运行时类型或 legacy evaluator helper

后续新功能应优先沿着 `source -> ast -> expand -> HIR -> MIR -> LIR -> bytecode -> register VM` 这条线推进，而不是继续扩大对 `evaluator.py` 的直接依赖。

## Compile-Time Runtime 现状

当前 macro body 执行仍复用 lowering 与 IR VM，但入口已经收敛到 compile-time facade：

- macro 定义捕获的是 compile-time environment facade，而不是在 `qy.macro` 中直接依赖 `Environment` 类型。
- compile-time 可用 binding 当前等于“定义时环境中的现有 binding 快照”加上展开期注入的 `gensym` 与 `capture`。
- compile-time effect 继续受 `effect_policy` 控制；macro body 其它失败会统一包装成 `failed during compile-time evaluation` diagnostics。

这仍是过渡实现，不代表 compile-time/runtime capability 已完全隔离，但边界已经比直接暴露 evaluator 类型更清晰。

## Macro Hygiene 现状

当前 macroexpand 已实现最小 hygiene：

- macro 引入的局部 binder（`let` binding、`lambda` params、`defun/component` params、`handle` params）会在展开后自动 rewrite 成稳定的 hidden symbol，避免捕获调用点同名 symbol。
- macro 引入的自由 symbol 默认按定义点绑定解析；展开 trace/source map 会记录原始 symbol 与 rewritten symbol 的映射关系。
- 普通程序里的 `quote` 仍保持边界，不会继续展开或 rewrite 内部数据。

如果确实需要显式捕获调用点 binding，目前可在 macro body 中使用 `(capture form)`：

- 默认 hygiene：`(cons '+ ...)` 会固定到 macro 定义点的 `+`。
- 显式捕获：`(cons (capture '+) ...)` 会保留调用点的 `+`，允许用户有意让局部 binding 参与解析。

`MacroExpansionTrace.renames` 与 `MacroExpansion.source_map[*].renames` 现在会暴露这些 rewrite，供后续 diagnostics / LSP 消费。

## CLI 调试命令

当前 CLI 提供四个调试命令用于观察各阶段产物：

```shell
qy expand examples/validation/00_host_arithmetic.qy
qy hir examples/validation/00_host_arithmetic.qy
qy mir examples/validation/00_host_arithmetic.qy
qy bytecode examples/validation/09_register_vm_tail_call.qy
```

四个命令都支持 stdin：

```shell
cat examples/validation/00_host_arithmetic.qy | qy mir -
printf '(+ 1 2)\n' | qy bytecode -
```

约定：

- 正常产物输出到 stdout。
- diagnostics 输出到 stderr。
- 若任何阶段产生 error 级 diagnostics，命令以退出码 `1` 返回。
- `mir` 与 `bytecode` 输出会保留 instruction 的 `SourceSpan`，便于 review 时回到源码位置。
