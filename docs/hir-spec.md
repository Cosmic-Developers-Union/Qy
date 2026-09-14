# Qy HIR 语言规范

## §0 目的与受众

本文档是 Qy HIR（高层语义 IR）的**正式语言规范**，是 HIR 形态的规范真源。它面向：

- 为 pipeline 的 HIR 阶段编写测试的工程师（可对照此文档断言 IR 节点形状）；
- 阅读 `qy/passes/hir/lower.py` 的贡献者（每条 lowering 规则在 §5 有对应条目）；
- 维护 analyzer / LSP / formatter 的工程师（这些工具应能消费符合本规范的 HIR）。

本文档规定：

- HIR 的 EBNF 文法；
- 每个节点的字段语义与不变量；
- HIR verifier 应当检查的不变量；
- 从 macroexpanded syntax datum 到 HIR 的 lowering 映射。

本文档**不**规定：

- HIR→MIR 的 lowering（见 `docs/mir-spec.md`）；
- 高层边界与设计意图（见 `docs/ir-design.md` §2）；
- 语言核心语义（见 `docs/op.md`、`LANGUAGE.md`）。

实现真源：`qy/ir/hir/node.py`、`qy/passes/hir/lower_pass.py`、`qy/passes/hir/lower.py`。

## §1 层定位

HIR 是**高层语义 IR**：它在 macroexpand 之后的 core-ast 之上构造。

它**回答**：

- 这个表达式语义上是什么？
- 它绑定到哪个 symbol-space binding？
- 它是哪类 operator / function / effect / module construct？
- 哪些控制结构必须保留为结构化节点？
- 哪些事实已经能被静态分析？

它**不**回答：

- 最后怎么跳转；
- 用几个寄存器；
- 怎么编码；
- register VM 怎么执行。

边界与设计意图详见 `docs/ir-design.md` §2；HIR→MIR 的 lowering 详见 `docs/mir-spec.md` §5。

## §2 EBNF 文法

### Legend

- `xxx?`：零或一次
- `xxx*`：零或多次
- `xxx+`：一或多次
- `xxx | yyy`：备选
- `xxx , yyy`：并列项（用于结构体字段与元组元素）
- **粗体关键字**：保留字
- `Symbol`、`SourceSpan`、`Form`、`ImportSpec`、`Diagnostic`、`OperatorKind`、`TypeName`：来自既有模块的类型（详见 §2.1）

### 2.1 复用类型

| 类型 | 来源 | 说明 |
| --- | --- | --- |
| `Symbol` | `qy.frontend.reader` | 不可变 interned 标识符；唯一 equality |
| `SourceSpan` | `qy.frontend.reader` / `qy.errors` | source 位置；line/column/offset/长度 |
| `Form` | `qy.frontend.reader` | syntax datum：`Symbol \| Chain`（immutable） |
| `ImportSpec` | `qy.import_.parse` | import 描述（name/alias/...) |
| `Diagnostic` | `qy.diag` | 编译/诊断 |
| `OperatorKind` | `qy.core` | 算子分类 |
| `TypeName` | `qy.core` | 类型名字符串（type-system 中类型标签的字符串名） |

### 2.2 顶层

```text
ProgramIR        := "ProgramIR" "{" "body" ":" IRExpr+ "," "diagnostics" ":" Diagnostic* "}"

IRExpr           := AllExpr | ApplyExpr | AssertExpr | CacheExpr | CallExpr | CondExpr
                  | DefeffectExpr | DefineExpr | DefunExpr | FromImportExpr
                  | HandleExpr | LambdaExpr | LetExpr | LiteralExpr | MacroExpr
                  | ModuleExpr | ParallelExpr | PerformExpr | PipelineExpr
                  | QuoteExpr | RaceExpr | ResumeExpr | RuntimeEvalExpr
                  | SymbolRefExpr | UnresolvedSymbolExpr
```

22 个 IRExpr 成员必须穷尽、无遗漏；union 顺序见 `qy/ir/hir/node.py:383-409`。

### 2.3 绑定与作用域

```text
BindingSource    := "define" | "defeffect" | "defun" | "lambda-param" | "let-binding"
                  | "handler-param" | "macro-param" | "module" | "import" | "builtin"
                  | "default-literal" | "unresolved"

SymbolSpace      := "SymbolSpace" "{" "name" ":" string "," "bindings" ":" {Symbol: int}* "," "parent" ":" SymbolSpace? "}"

BindingRef       := "BindingRef" "{" "id" ":" int "," "symbol" ":" Symbol "," "source" ":" BindingSource
                       "," "type_name" ":" TypeName "," "owner_space" ":" SymbolSpace
                       "," "operator_kind" ":" OperatorKind? "," "eager_arguments" ":" bool = true
                       "," "continuous" ":" bool = false "," "value" ":" any? "}"

Binding          := "Binding" "{" "symbol" ":" Symbol "," "source" ":" BindingSource
                       "," "type_name" ":" TypeName "," "owner_space" ":" SymbolSpace?
                       "," "operator_kind" ":" OperatorKind? "," "eager_arguments" ":" bool = true
                       "," "continuous" ":" bool = false "," "value" ":" any? "}"
```

### 2.4 表达式节点

```text
LiteralExpr           := "{" "value" ":" any "," "type_name" ":" TypeName "," "span" ":" SourceSpan? "," "source_symbol" ":" Symbol? "}"

SymbolRefExpr         := "{" "symbol" ":" Symbol "," "binding" ":" Binding "," "span" ":" SourceSpan? "}"

UnresolvedSymbolExpr  := "{" "symbol" ":" Symbol "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

QuoteExpr             := "{" "form" ":" Form "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

RuntimeEvalExpr       := "{" "expression" ":" IRExpr "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

CacheExpr             := "{" "expression" ":" IRExpr "," "cache_key" ":" any "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

CallExpr              := "{" "operator" ":" IRExpr "," "args" ":" IRExpr* "," "span" ":" SourceSpan?
                            "," "type_name" ":" TypeName "," "tail_position" ":" bool = false
                            "," "continuous" ":" bool = false "}"

LetBinding            := "{" "symbol" ":" Symbol "," "value" ":" IRExpr "}"

LetExpr               := "{" "bindings" ":" LetBinding+ "," "body" ":" IRExpr* "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

LambdaExpr            := "{" "params" ":" Symbol+ "," "body" ":" IRExpr* "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

DefunExpr             := "{" "name" ":" Symbol "," "params" ":" Symbol+ "," "body" ":" IRExpr*
                            "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

DefineExpr            := "{" "name" ":" Symbol "," "value" ":" IRExpr "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

PipelineExpr          := "{" "body" ":" IRExpr+ "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

ParallelExpr          := "{" "exprs" ":" IRExpr+ "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

AllExpr               := "{" "exprs" ":" IRExpr+ "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

RaceExpr              := "{" "exprs" ":" IRExpr+ "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

ApplyExpr             := "{" "function" ":" IRExpr "," "args" ":" IRExpr "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

MacroExpr             := "{" "name" ":" Symbol "," "params" ":" Symbol+ "," "body" ":" IRExpr*
                            "," "raw_body" ":" tuple "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

DefeffectExpr         := "{" "name" ":" Symbol "," "resumable" ":" bool "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

CondClause            := "{" "condition" ":" IRExpr "," "result" ":" IRExpr "}"

CondExpr              := "{" "clauses" ":" CondClause+ "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

FromImportExpr        := "{" "module" ":" Symbol "," "specs" ":" ImportSpec+ "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

ModuleExpr            := "{" "name" ":" Symbol "," "body" ":" IRExpr*
                            "," "export_names" ":" Symbol* = () "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

PerformExpr           := "{" "effect" ":" Symbol "," "argument" ":" IRExpr "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

EffectHandler         := "{" "effect" ":" Symbol "," "arg_name" ":" Symbol "," "continuation_name" ":" Symbol "," "body" ":" IRExpr* "}"

HandleExpr            := "{" "expression" ":" IRExpr "," "handlers" ":" EffectHandler+ "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

ResumeExpr            := "{" "continuation" ":" IRExpr "," "value" ":" IRExpr "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"

AssertExpr            := "{" "condition" ":" IRExpr "," "message" ":" IRExpr? "," "span" ":" SourceSpan? "," "type_name" ":" TypeName "}"
```

`SymbolRefExpr.type_name` 在运行时从 `binding.type_name` 派生（见 `node.py:175-176`）；构造时无需显式传入。

## §3 节点目录

本节按 `IRExpr` union 顺序逐节点给出：字段语义、不变量、构造约束。

### 3.1 ProgramIR

| 字段 | 含义 |
| --- | --- |
| `body` | top-level 表达式序列；macroexpand 后顺序保持；非空 |
| `diagnostics` | lowering 阶段产生的诊断集合 |

不变量：

- `ProgramIR.ok`（派生属性）当且仅当 `diagnostics` 中无 `severity == "error"`。
- `body` 顺序与 source 中 top-level form 顺序一一对应。

构造约束：仅 `qy.passes.hir.lower_pass.LowerHIRPass` 允许构造。

### 3.2 绑定与作用域

#### SymbolSpace

| 字段 | 含义 |
| --- | --- |
| `name` | 空间的可读名（用于诊断） |
| `bindings` | symbol → 本空间 slot index 的局部表；不同空间用相同 symbol 不冲突 |
| `parent` | 父空间；根空间为 `None` |

不变量：

- `SymbolSpace` 形成一棵树而非 DAG（每个空间至多一个父）。
- `bindings` 中 key 是已 intern 的 `Symbol`；value 是该符号在本空间的稳定 slot index。

构造约束：`module` / `lambda` / `let` / `handle` / `macro` 展开创建新 `SymbolSpace`。

#### BindingSource

`BindingSource` 是一个 enum literal（12 个来源）：

| 来源 | 出现位置 |
| --- | --- |
| `define` | `(define x e)` |
| `defeffect` | `(defeffect n r)` |
| `defun` | `(defun f (x) body)` |
| `lambda-param` | `(lambda (x) body)` 的 `x` |
| `let-binding` | `(let ((x e)) body)` 的 `x` |
| `handler-param` | `(handle e ((eff arg k) body))` 的 `arg` 与 `k` |
| `macro-param` | `(macro n (x) body)` 的 `x` |
| `module` | module 体内 binding |
| `import` | `(from ...)` 引入的 binding |
| `builtin` | profile / pre-symbol-space-chain 提供的 binding |
| `default-literal` | literal resolver 提供的 binding（如 `+`、`cons`） |
| `unresolved` | 尚未解析成功的符号 |

#### BindingRef / Binding

`BindingRef` 与 `Binding` 是同一意图的两种封装：

- `BindingRef` 携带稳定 `id: int`，供后续 pass 做跨变换 identity 比较；
- `Binding` 是简化形式，缺 `id`，常用于不需要 identity 跟踪的场景。

| 字段 | 含义 |
| --- | --- |
| `id`（仅 BindingRef） | 稳定 binding id，由 binding 分配器单调生成 |
| `symbol` | 该 binding 引入的 `Symbol` |
| `source` | `BindingSource` |
| `type_name` | 静态类型标签 |
| `owner_space` | 该 binding 所在的 `SymbolSpace`；`Binding.owner_space?` 可为 `None` |
| `operator_kind` | 若绑定到算子声明，则填算子分类；否则 `None` |
| `eager_arguments` | 默认 `true`；若为 `false`，该算子为 control operator，参数按需求值 |
| `continuous` | 见 `OperatorSignature.continuous`；纯算子标记 |
| `value` | 可选预计算值（仅 `compare=False, repr=False`；不参与等价性比较） |

不变量：

- `Binding.continuous` 与 `Binding.operator_kind` 协同：`Pure` / `Control` / `Effect` / `Meta` 算子中，`Pure` 通常为 `continuous=True`。
- 同一 `SymbolSpace` 内同一 `Symbol` 至多一个 binding（define-once）。

构造约束：BindingRef 由 `binding_addr_alloc` 类设施分配 id；Binding 多为中间表示。

### 3.3 值 / 引用

#### LiteralExpr

| 字段 | 含义 |
| --- | --- |
| `value` | literal 值；可为 number / string / char / 宿主引用等 |
| `type_name` | 该 literal 的静态类型 |
| `span` | source 位置 |
| `source_symbol` | 该 literal 来自的 syntax symbol（如有） |

不变量：literal 在 reader 阶段可能尚未定型；`value` 经 host-value canonicalization 校准（见 `lower.py:410-427`）。

#### SymbolRefExpr

| 字段 | 含义 |
| --- | --- |
| `symbol` | source 中的 syntax symbol |
| `binding` | resolved binding |
| `span` | source 位置 |

派生属性：`type_name` 等于 `binding.type_name`。

不变量：

- `binding` 不为空；若 binding 解析失败，须使用 `UnresolvedSymbolExpr`（见下），不得伪装 resolved。
- `binding.operator_kind` 与节点所在位置的算子使用语义一致。

#### UnresolvedSymbolExpr

| 字段 | 含义 |
| --- | --- |
| `symbol` | source 中的 syntax symbol |
| `span` | source 位置 |
| `type_name` | 固定 `"unknown"` |

不变量：

- 不携带 `binding`；明确标记解析失败。
- 后续 pass（特别是 MIR lowering）不得把它当成 `SymbolRefExpr` 处理；它必须要么被解析为 `SymbolRefExpr`，要么生成 diagnostic。

#### QuoteExpr

| 字段 | 含义 |
| --- | --- |
| `form` | syntax datum；原始 `Form`，不展开 |
| `span` | source 位置 |
| `type_name` | 固定 `"any"`（quote 不求值） |

不变量：`form` 是 `Form` 类型；不得预先求值；不得混入 runtime value。

### 3.4 调用 / 高层控制

#### CallExpr

| 字段 | 含义 |
| --- | --- |
| `operator` | 被调用的表达式 |
| `args` | 实参列表；元组；可为空（0-arity 算子） |
| `span` | source 位置 |
| `type_name` | 由 lowering 填入；常见为 `"any"` 或 operator 返回类型 |
| `tail_position` | 是否处于 tail position；MIR 借此决定使用 `CALL` 还是 `TAIL_CALL` |
| `continuous` | 该调用是否属于 IR 层不可中断点；见下 |

`continuous` 的语义目标：

- 当 `continuous=True` 时，MIR/LIR lowering 不得在该指令所在区间内插入 terminator、分支、scope 切换、effect-region 边界。
- 三个 verifier 都对此有专门检查（见 `docs/ir-design.md` §1.2）。
- 标志来源：对应 `Binding.operator_kind == Pure` 的算子，`OperatorSignature.continuous` 通常为 `True`。

不变量：

- `args` 的语义由 `operator` 决定（eager or lazy）；HIR 不强制求值顺序。
- `operator` 不允许是字面 `SymbolRefExpr` 当且仅当该 binding 不存在；同样以 `UnresolvedSymbolExpr` 标记。

构造约束：所有 `(op arg*)` 形式都最终产生 `CallExpr`（包括 `component` / 一般 head）；特殊 head（`let` / `cond` / ...）则单独构造对应节点（见 §5）。

#### RuntimeEvalExpr

| 字段 | 含义 |
| --- | --- |
| `expression` | 被 `eval` 的 IR 表达式；通常来自 `quote`/`quasiquote` 构造的 syntax |
| `span` | source 位置 |
| `type_name` | 固定 `"any"` |

不变量：`eval` 在 Qy 中是运行时能力；`RuntimeEvalExpr` 是 `eval` 算子的 HIR 节点封装，不在编译期求值。

#### CacheExpr

| 字段 | 含义 |
| --- | --- |
| `expression` | 被缓存求值的表达式 |
| `cache_key` | 缓存键；通常为静态可哈希值 |
| `span` | source 位置 |
| `type_name` | 固定 `"any"` |

#### ApplyExpr

| 字段 | 含义 |
| --- | --- |
| `function` | 被调用的函数表达式 |
| `args` | 实参表达式（运行时 chain） |

不变量：`args` 是单个 `IRExpr`（取值时为运行时 chain）；`ApplyExpr` 把运行时 chain 拆成多参数调用。

### 3.5 局部结构

#### LetBinding / LetExpr

```text
LetBinding := { symbol: Symbol, value: IRExpr }
LetExpr    := { bindings: LetBinding+, body: IRExpr*, ... }
```

不变量：

- `LetExpr` 创建新 `SymbolSpace`；每个 binding 在新空间内 define-once。
- body 在新空间内求值；body 完成后旧空间恢复。
- `LetExpr.bindings` 至少 1 个。

#### LambdaExpr

| 字段 | 含义 |
| --- | --- |
| `params` | 形参列表（≥ 1 个） |
| `body` | 函数体（≥ 1 个） |

不变量：

- 创建新 `SymbolSpace`；params 在该空间为 `lambda-param` 来源 binding。
- `body` 在该空间内顺序求值。

#### DefunExpr

| 字段 | 含义 |
| --- | --- |
| `name` | 函数名 |
| `params` | 形参列表 |
| `body` | 函数体 |

不变量：语义上等价于 `DefineExpr(name, LambdaExpr(params, body))`；但 lowering 直接产生 `DefineExpr` 包装形式（见 §5）。

#### DefineExpr

| 字段 | 含义 |
| --- | --- |
| `name` | 绑定名 |
| `value` | 绑定值表达式 |

不变量：

- 当前 `SymbolSpace` 内 `name` 不得已绑定（define-once）。
- `define` 只**提升 binding**，不**提升 RHS 求值**——RHS 仍按运行时顺序求值；这条性质对 pipeline（如 `pipeline (echo x) (define x (op ...))`）至关重要（见 `docs/ir-design.md` §2.5）。
- 读取未完成 RHS 的 binding 是**显式 effort**，不是 Python exception。

### 3.6 顺序 / 并发结构

#### PipelineExpr

| 字段 | 含义 |
| --- | --- |
| `body` | 顺序执行的表达式序列；结果为最后一个 |

不变量：求值顺序保留；与 `do` / `begin` 等价；无 effect 边界插入。

#### ParallelExpr / AllExpr / RaceExpr

三者在 HIR 中形态一致：

| 节点 | 语义 |
| --- | --- |
| `ParallelExpr` | 标记一组表达式求值顺序无关；VM 可并行，但不要求并行 |
| `AllExpr` | barrier continuation；全部分支完成后父级恢复 |
| `RaceExpr` | first-resume-wins；最先恢复 parent continuation 的分支获胜 |

不变量：`exprs` 至少 1 个；每个 expr 都在独立的 thunk 中求值（由 MIR 引入 thunk 函数）。

### 3.7 算子 / 模块

#### MacroExpr

| 字段 | 含义 |
| --- | --- |
| `name` | macro 名 |
| `params` | macro 形参 |
| `body` | macro 转换后的 body（IR 形式，供后续 pass 使用） |
| `raw_body` | macro 的原始 syntax datum；保留供 hygiene trace |

不变量：

- macro 转换发生在 compile-time；`MacroExpr` 在 HIR 中是声明节点，不在 runtime 求值。
- `body` 与 `raw_body` 同步存在；前者是 lowered 形式，后者是 source 形式。

#### DefeffectExpr

| 字段 | 含义 |
| --- | --- |
| `name` | effect 名 |
| `resumable` | 是否可恢复；不可恢复的 effect 不接受 `resume` |

不变量：当前 `SymbolSpace` 内 `name` define-once。

#### FromImportExpr

| 字段 | 含义 |
| --- | --- |
| `module` | 被引入的 module |
| `specs` | 引入项列表（含 name / alias） |

不变量：

- import alias 冲突按当前空间的 define-once 处理。
- `from` 是受 `exports` 限制的选择性 fold。

#### ModuleExpr

| 字段 | 含义 |
| --- | --- |
| `name` | module 名 |
| `body` | module 体 |
| `export_names` | export view 中的符号名（默认空） |

不变量：

- module 创建新 `SymbolSpace`，但 `module` 本身可被引用 / fold。
- export view 是 module 边界的可见性描述。

### 3.8 effect

#### PerformExpr

| 字段 | 含义 |
| --- | --- |
| `effect` | 被 perform 的 effect 名 |
| `argument` | effect 实参 |

不变量：

- `effect` 必须已在某 `SymbolSpace` 由 `defeffect` 声明。
- perform 不被 lower 成普通函数调用；它是 IR 层显式控制边。

#### EffectHandler / HandleExpr

```text
EffectHandler := { effect: Symbol, arg_name: Symbol, continuation_name: Symbol, body: IRExpr* }
HandleExpr    := { expression: IRExpr, handlers: EffectHandler+, ... }
```

不变量：

- `HandleExpr.handlers` 至少 1 个。
- 每个 handler 的 `effect` 必须已被 `defeffect` 声明。
- handler 在新的 `SymbolSpace` 中求值；`arg_name` 是 `handler-param`，`continuation_name` 同。
- handler body 内可用 `resume`（产生 `ResumeExpr`）。

#### ResumeExpr

| 字段 | 含义 |
| --- | --- |
| `continuation` | `k`（在 handler 中由 `continuation_name` 引入的 binding） |
| `value` | 注入到 resume target 的值 |

不变量：

- 仅在 `HandleExpr` 的 handler body 内合法出现。
- 仅当对应 effect 的 `resumable=True` 时合法。

### 3.9 AssertExpr

| 字段 | 含义 |
| --- | --- |
| `condition` | 断言条件 |
| `message` | 可选失败消息 |

不变量：`condition` 必须可求值；MIR 把它 lower 成 `BRANCH` + `RAISE_EFFECT` 序列。

## §4 Verifier 规则

当前实现没有独立 HIR verifier（见 `qy/ir/hir/`、`qy/passes/hir/`）；下表给出 verifier 应检查的不变量（用于补齐 verifier 时对照）。

| 编号 | 不变量 |
| --- | --- |
| H1 | 所有 `SymbolRefExpr` 必有非空 `binding`；解析失败的符号必须用 `UnresolvedSymbolExpr`，不得伪装 |
| H2 | 同一 `SymbolSpace` 内同一 `Symbol` 至多一个 binding（define-once） |
| H3 | 所有 `IRExpr` 构造合法：每节点必满足 §3 中字段不变量；特殊节点 arity 合法（如 `LetExpr.bindings ≥ 1`、`CondExpr.clauses ≥ 1`、`HandleExpr.handlers ≥ 1`、`PipelineExpr.body ≥ 1`） |
| H4 | `CallExpr.continuous=True` 当且仅当对应 `Binding.operator_kind ∈ {Pure}` 且 `OperatorSignature.continuous=True` |
| H5 | `CallExpr.tail_position` 仅在合法位置（函数最末一个表达式、`cond` clause 的 result、`if` 分支、`pipeline` body 末项、`let` body 末项、`handle` body 末项等） |
| H6 | `HandleExpr` 内 effect 必须已被 `defeffect` 声明（解析期检查） |
| H7 | `ResumeExpr` 仅出现在 `HandleExpr` 的 handler body 内；对应 effect 必须 `resumable=True` |
| H8 | `PerformExpr.effect` 必须已被 `defeffect` 声明 |
| H9 | `ModuleExpr.export_names` 中的每个符号都已在 module body 内 define |
| H10 | `FromImportExpr.specs` 中的每个名字都已在目标 module 的 export view 中 |
| H11 | `QuoteExpr.form` 是合法 `Form`（`Symbol \| Chain`），不得是 runtime value |
| H12 | `DefineExpr.name` 在当前 `SymbolSpace` 内未绑定；同 scope 内 `define` 不重复 |
| H13 | 读取未完成 RHS 的 binding 应被静态标记为 effort（pending binding） |
| H14 | `MacroExpr.raw_body` 与 `body` 在 macro 展开后保持同步 |

## §5 Source → HIR 映射

本节给出 macroexpanded syntax datum → HIR 节点的映射。**实现真源**：`qy/passes/hir/lower.py`（Form→HIR lowering）。

> **注意**：文件命名上 `qy/passes/hir/lower.py` 容易被误读为 HIR→MIR；实际上它是 **Form→HIR**，HIR→MIR 在 `qy/passes/mir/normalize.py`。

### 5.1 顶层 dispatch

`lower.py:221-267`（Chain 路径）与 `lower.py:307-353`（tuple 路径）根据 operator name 分派到 `_lower_<name>` helper；非特殊 head 落入通用 `CallExpr` 构造（Chain 路径行 290-296；tuple 路径行 373-379）。

### 5.2 映射表

| Source form | HIR 节点 | 实现位置 |
| --- | --- | --- |
| `(quote x)` | `QuoteExpr(form=x)` | `_lower_quote` `lower.py:492-496` |
| `` `(x ,y ,@z) `` | 展开为 `quasiquote`/`unquote`/`unquote-splicing` 后再 lower | `_lower_quasiquote` `lower.py:499-511` |
| `(eval e)` | `RuntimeEvalExpr(expression=lower(e))` | `_lower_eval` `lower.py:587-598` |
| `(cond (c e) ...)` | `CondExpr(clauses=...)` | `_lower_cond` `lower.py:628-647` |
| `(let ((x e) ...) body...)` | `LetExpr(bindings=..., body=...)` | `_lower_let` `lower.py:650-691` |
| `(lambda (x...) body...)` | `LambdaExpr(params=..., body=...)` | `_lower_lambda` `lower.py:694-710` |
| `(component ...)` | `CallExpr(operator=component-binding, args=...)` | `_lower_component` `lower.py:713-751`（遗留；见 §7） |
| `(defun f (x...) body...)` | `DefineExpr(name=f, value=LambdaExpr(...))` | `_lower_defun` `lower.py:754-780` |
| `(defeffect n r)` | `DefineExpr(name=n, value=DefeffectExpr(name=n, resumable=r))` | `_lower_defeffect` `lower.py:783-812` |
| `(module n body...)` | `ModuleExpr(name=n, body=...)` | `_lower_module` `lower.py:815-846` |
| `(from m [name : alias]*)` | `FromImportExpr(module=m, specs=...)` | `_lower_from` `lower.py:849-868` |
| `(perform e a)` | `PerformExpr(effect=e, argument=lower(a))` | `_lower_perform` `lower.py:871-888` |
| `(handle e ((e k b) ...))` | `HandleExpr(expression=lower(e), handlers=...)` | `_lower_handle` `lower.py:891-973` |
| `(resume k v)` | `ResumeExpr(continuation=lower(k), value=lower(v))` | `_lower_resume` `lower.py:1000-1017` |
| `(assert c m?)` | `AssertExpr(condition=lower(c), message=lower(m) if m)` | `_lower_assert` `lower.py:1020-1032` |
| `(define x e)` | `DefineExpr(name=x, value=lower(e))` | `_lower_define` `lower.py:1388-1401` |
| `(pipeline e...)` | `PipelineExpr(body=...)` | `_lower_pipeline` `lower.py:1404-1419` |
| `(parallel e...)` | `ParallelExpr(exprs=...)` | `_lower_parallel` `lower.py:1422-1429` |
| `(all e...)` | `AllExpr(exprs=...)` | `_lower_all` `lower.py:1432-1439` |
| `(race e...)` | `RaceExpr(exprs=...)` | `_lower_race` `lower.py:1442-1449` |
| `(apply f args)` | `ApplyExpr(function=lower(f), args=lower(args))` | `_lower_apply` `lower.py:1452-1463` |
| `(cache e k)` | `CacheExpr(expression=lower(e), cache_key=k)` | `_lower_cache` `lower.py:1466-1481` |
| `(macro n (p...) body...)` | `MacroExpr(name=n, params=..., body=..., raw_body=...)` | `_lower_macro` `lower.py:601-625` |
| bare symbol 在作用域中 | `SymbolRefExpr(symbol, binding)` | `_lower_symbol` `lower.py:430-489` |
| bare symbol 不在作用域且非字面 | `UnresolvedSymbolExpr(symbol)` | `lower.py:488` |
| literal / 其他 atoms | `LiteralExpr(value, type_name)` | `lower.py:299-302`；host-value 规范化 `lower.py:410-427` |
| 通用 head `(op a...)` | `CallExpr(operator=lower(op), args=..., tail_position=..., continuous=False)` | `lower.py:290-296`（Chain）/ `lower.py:373-379`（tuple） |

### 5.3 关键 lowering 规则

- **连续算子传播**：当前实现 `CallExpr.continuous` **永远为 `False`**（四个构造点均未传 `continuous=`，见 §7 事实 2）。spec 要求 HIR `CallExpr.continuous` 与对应 `Binding.continuous` 一致；该要求尚未被 lowering 实现。
- **`tail_position` 推断**：`lower_call`（`normalize.py:275-282`）在 MIR 阶段根据所在位置决定 `tail_position`；HIR 阶段不在 lowering 时设置，仅在 MIR 调用层判定。
- **`define` 的 binding 提升**：HIR 阶段记录 binding；RHS 求值仍在运行时执行。
- **`defun` / `defeffect` 包装**：`defun` 直接产生 `DefineExpr` 包装 `LambdaExpr`；`defeffect` 直接产生 `DefineExpr` 包装 `DefeffectExpr`（`lower.py:783-812`）。

## §6 工作样例

### 6.1 算术 + cond

**Source**（取自 `examples/validation/00_host_arithmetic.qy`，略改）：

```lisp
(define (square x) (* x x))
(square 12)
```

**对应 HIR（伪 dump）**：

```text
ProgramIR {
  body = [
    DefineExpr {
      name = square
      value = LambdaExpr {
        params = (x,)
        body = (
          CallExpr {
            operator = SymbolRefExpr { symbol = *, binding = <builtin: *> }
            args = (SymbolRefExpr { symbol = x, binding = <lambda-param: x> },
                    SymbolRefExpr { symbol = x, binding = <lambda-param: x> })
            tail_position = True
            continuous = False
          },
        )
        type_name = function
      }
      type_name = function
    },
    CallExpr {
      operator = SymbolRefExpr { symbol = square, binding = <defun: square> }
      args = (LiteralExpr { value = 12, type_name = int },)
      tail_position = True
      continuous = False
    },
  ]
  diagnostics = ()
}
```

要点：

- `defun` 在 HIR 中表现为 `DefineExpr` 包装 `LambdaExpr`；
- `CallExpr` 携带 `tail_position=True`（函数体最末调用），由 MIR lowering 转换为 `TAIL_CALL` terminator；
- `*` 与 `square` 的 `binding` 已解析；`*` 是 `default-literal`，`square` 是 `defun`。

### 6.2 handle / perform / resume

**Source**：

```lisp
(handle
  (on divide-by-zero () k (resume k 1))
  (+ (/ 1 0) (/ 1 0)))
```

**对应 HIR（伪 dump）**：

```text
CallExpr {
  operator = HandleExpr {
    expression = CallExpr {
      operator = SymbolRefExpr { symbol = +, binding = <builtin: +> }
      args = (
        CallExpr { operator = SymbolRefExpr { symbol = /, binding = <builtin: /> },
                   args = (LiteralExpr 1, LiteralExpr 0), tail_position = False },
        CallExpr { operator = SymbolRefExpr { symbol = /, binding = <builtin: /> },
                   args = (LiteralExpr 1, LiteralExpr 0), tail_position = True },
      )
    }
    handlers = (
      EffectHandler {
        effect = divide-by-zero
        arg_name = <ignored>
        continuation_name = k
        body = (ResumeExpr { continuation = SymbolRefExpr { symbol = k },
                             value = LiteralExpr 1 },)
      },
    )
  }
  args = ()
}
```

要点：

- `HandleExpr.expression` 是受保护表达式；`handlers` 列表中的每个 `EffectHandler` 给出 effect 集的处理函数。
- handler body 内的 `resume k 1` 产生 `ResumeExpr`。

## §7 现状与偏差

### 7.1 `continuous` 标志未被传播

`CallExpr.continuous` 当前**永远为 `False`**：

- `lower.py` 的四个 `CallExpr(...)` 构造点（行 290-296、373-379、731-737、746-751）均未传 `continuous=`，字段保留默认 `False`。
- `Binding.continuous` 已从 `OperatorSignature.continuous` 复制（`lower.py:1227`），但 `CallExpr` 的构造未读取 `binding.continuous`。

这意味着：

- MIR / LIR verifier 中的 `_verify_continuous_run` 永远不 fire；
- `docs/ir-design.md §1.2` 描述的"连续算子静态不变量"目前是**声明但未生效**。

spec 给出 `continuous` 的**目标语义**（不可中断点，verifier 应拒 split），实现需补齐 set 路径。这是 Phase B / Phase C 边界工作的一部分。

### 7.2 `component` 仍存在

`lower.py:713-751` 的 `_lower_component` 仍把 `(component ...)` 降为对 `component` 算子的 `CallExpr`。`component` 不是语言核心节点，但 spec 保留这条映射条目供溯源。

### 7.3 无独立 HIR verifier

`docs/ir-design.md §2.6` 列出的 verifier 规则当前无对应实现；`H1-H14` 的检查散落在 `lower.py` 的 lowering 阶段（如未解析符号立即生成 `UnresolvedSymbolExpr`、module import 失败生成 diagnostic 等），并不构成独立的 verifier pass。

### 7.4 Binding 与 BindingRef 并存

`Binding` 与 `BindingRef` 同时在 `IRExpr` 之外存在；当前 HIR 主体（`SymbolRefExpr.binding`）使用 `Binding`，而 `BindingRef` 多见于 binding address allocation 路径。spec 给出两者语法与字段语义，但**当前 `SymbolRefExpr` 实际承载 `Binding` 而非 `BindingRef`**。

### 7.5 `PipelineExpr.body` 与其他序列结构

`PipelineExpr.body` 须至少 1 个表达式；`CondExpr.clauses` 同；`LetExpr.bindings` 同。这些 arity 规则在 spec 中标注，但当前 lowering 不显式报错（如空 pipeline 会原样 lower）；若未来 HIR verifier 落地，应在该阶段统一拦截。