# Qy Pipeline

本文档描述 Qy 唯一编译与执行管线。Qy 不保留可选 runtime backend；register VM 是唯一执行器。

## 管线概览

```text
source (文本)
  -> CST (Concrete Syntax Tree, trivia-preserving)
  -> raw forms (reader macros applied)
  -> surface forms (quote/quasiquote sugar expanded)
  -> macro expand (with hygiene)
  -> HIR
  -> MIR
  -> LIR
  -> bytecode
```

管线在 `emit.bytecode` pass 处结束。register VM 在管线外部执行 bytecode：`Qy.evaluate_source(...)` 内部调用 `build_default_pipeline().run(source)` 得到 bytecode，再交给 `RegisterVirtualMachine` 执行。

## 分层边界

每层有且只有一个职责；禁止跨层解释语义。

| 层 | Pass 名称 | 输入 | 输出 | 产生 diagnostics | 是否依赖 RuntimeSpace |
| --- | --- | --- | --- | --- | --- |
| CST 解析 | `frontend.cst_parse` | 源码字符串 | `CstProgram`（trivia-preserving CST） | 是，parser error | 否 |
| Reader Macro | `frontend.reader_macro` | `CstProgram` | raw `list[Form]`；每个 form 是 `symbol` 或不可变 `chain` | 是，reader macro error | 否 |
| Surface Normalize | `frontend.surface_normalize` | raw `list[Form]` | default-dialect `list[Form]`，如 `'x` → `(quote x)` | 否 | 否 |
| Macro Expand | `macro.expand` | surface-dialect `list[Form]` | `MacroExpansion(forms, diagnostics, traces)` | 是，展开错误、compile-time effect 错误 | 是，compile-time facade 捕获环境快照 |
| HIR Lower | `hir.lower` | macroexpanded `CoreProgram` | `ProgramIR`（resolved binding、structured control、operator/effect/module facts） | 是，未解析符号、arity、module import 等 | 是，只读取实例事实 |
| MIR Lower | `mir.lower` | `ProgramIR` | `MIRProgram`（CFG + virtual register + explicit control/effect flow） | 是，覆盖不到的 HIR 节点进入 MIR diagnostics | 否 |
| LIR Lower | `lir.lower` | `MIRProgram` | `LIRProgram`（Qy abstract machine IR，显式 frame / ss-chain / slot / continuation / handler） | 是 | 否 |
| Bytecode Emit | `emit.bytecode` | `LIRProgram` | `BytecodeProgram`（纯结构转换，不重新理解语义） | 是，沿用 LIR diagnostics | 否 |
| Register VM | *(管线外部)* | `BytecodeProgram` | 运行结果 / top-level 结果列表 | 运行期异常 | 是，执行时需要 runtime environment |

**跨层禁止规则**：

- reader 只负责源码到 `symbol` / `chain`；不得把 number、string 或其他 runtime value 提前塞进 raw AST。
- runtime value 与 Python value 必须分离；跨宿主对象只能以 host reference / adapter 进入后续阶段。
- bytecode compiler 不能重新理解 HIR/MIR 语义；语义 lowering 必须经由 LIR。
- MIR lowering 不能访问 Environment（不能查 runtime binding）。
- HIR 之上（reader/surface dialect/macroexpand）不得引入 bytecode/VM 特定的 representation。
- HIR、MIR、LIR 的详细独立约束见 `docs/ir-design.md`；新 rewrite 必须先归属到唯一一层。

## 阶段职责补充

### HIR

- 负责 resolved binding、operator declaration、effect declaration、module/fold、structured control；
- 保留对 analyzer / LSP 有意义的高层事实；
- 不允许 CFG、寄存器、bytecode、host ABI。

### MIR

- 把 HIR 结构化语义变成显式 CFG；
- 使用 virtual register；
- 显式表达 branch、tail call、effect flow、join；
- 不访问 runtime `Environment`，不承担 physical layout。

### LIR

- 完成 instruction selection、layout、register/frame 分配、host-call ABI、jump fixup、peephole、debug injection；
- 它是 VM-facing 但尚未最终编码的 Qy abstract machine IR；
- 它必须显式建模 virtual stack frame、continuation frame、handler frame / effect marker、symbol-space-chain enter / leave / copy / restore、lookup operation、binding slot read / complete / pending effort；
- `handle` / `perform` / `resume` 到 LIR 边界后不应再作为语言级指令存在，只能表现为 frame、continuation、ss-chain transition 与 CFG jump；
- 它不能只是 bytecode opcode 的别名层。

### Bytecode

- 只接收已经 verified 的 LIR；
- 只做 encode / pack / relocate / attach tables；
- 不再理解 binding、tail call、effect、module 等高层语义。

## 稳定 API 与删除对象

### Qy 类稳定 API

- `Qy.read` / `Qy.read_one` — 解析源码为 Form 序列
- `Qy.evaluate(expression)` — 求值单个表达式
- `Qy.evaluate_source(source)` / `Qy.evaluate_source_async(source)` — 求值源码字符串
- `Qy.evaluate_program(source)` — 求值多 form 程序，返回结果列表
- `Qy.evaluate_file(path)` — 求值文件
- `Qy.fmt(source)` — 格式化源码
- `Qy.register_pure` / `register_scope` / `register_control` / `register_effect` / `register_meta` — 注册自定义算子

### 管线 API

- `build_default_pipeline()` — 唯一管线工厂，返回 `Pipeline` 对象
- `compile_source_to_bytecode(source)` — 源码到 bytecode 的完整管线
- `compile_source_to_kind(source, kind)` — 源码到指定中间产物

### 运行时 API

- `RegisterVirtualMachine` — Python 寄存器 VM
- `RuntimeSpace`（`Environment` 为其类型别名） — 运行时符号空间

### 已删除对象（禁止回归）

- `Qy.macroexpand` / `Qy.macroexpand_source` — 已从 Qy 类移除（`macro/expand.py` 中仍有独立函数）
- `Qy.lower` / `Qy.lower_source` — 已从 Qy 类移除
- `Qy.lower_mir` / `Qy.compile_bytecode` / `Qy.evaluate_bytecode` — 已从 Qy 类移除
- `Qy.evaluate_ir` / `Qy.evaluate_ir_source` — 已删除
- `qy.ir_vm/` 目录与 `qy.ir_vm.*` public execution API — 已删除
- `Qy(backend=...)` 与 `EvaluationBackend` — 已删除
- `qy/evaluator.py` — 已删除
- `qy/register_vm.py`、`qy/virtual_stack.py` — 已删除
- `qy/lowering.py`、`qy/mir_lowering.py`、`qy/lir_lowering.py` — 已删除
- `qy/environment.py` — 已删除（`Environment` 现为 `RuntimeSpace` 的类型别名）

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

macro body 的 compile-time facade 仍是过渡实现：

- macro 定义捕获的是 compile-time environment facade（`MacroExpansionServices`），不直接依赖 `RuntimeSpace` 类型。
- compile-time 可用 binding 当前等于定义时环境中的现有 binding 快照，加上展开期注入的 `gensym` 与 `capture`。
- compile-time effect 受 `effect_policy` 控制；macro body 失败统一包装成 `failed during compile-time evaluation` diagnostics。
- legacy `qy/evaluator.py` 已删除，compile-time 执行路径已不再通过 evaluator 模块。

这仍是过渡实现，compile-time/runtime 能力未完全隔离，但边界已比直接暴露 evaluator 类型更清晰。

## Macro Hygiene 现状

当前 macroexpand 实现最小 hygiene：

- macro 引入的局部 binder（`let` binding、`lambda` / `defun` params、`handle` params）展开后自动 rewrite 为稳定 hidden symbol，避免捕获调用点同名 symbol。
- macro 引入的自由 symbol 默认按定义点绑定解析。
- 需要显式捕获调用点 binding 时，使用 `(capture form)`：
  - 默认 hygiene：`(cons '+ ...)` 固定到 macro 定义点的 `+`。
  - 显式捕获：`(cons (capture '+) ...)` 保留调用点的 `+`。

`MacroExpansionTrace.renames` 与 `MacroExpansion.source_map[*].renames` 暴露这些 rewrite，供 diagnostics / LSP 消费。
