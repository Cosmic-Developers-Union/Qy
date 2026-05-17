# Qy Full Roadmap

本文件不是最近一批工作的便签，而是 **Qy 从当前实现走到目标语言的完整路线图**。  
历史批次与已完成细节看 `report.md`；语言规范看 `LANGUAGE.md`；算子分层看 `docs/op.md`；阶段边界与 IR 约束看 `docs/pipeline.md`、`docs/ir-design.md`。

最近一次本地基线（2026-05-18）：

- `uv run python -m pytest -q`：363 passed
- `uv run ty check .`：passed
- `uv run python -m qy test.qy tests/qy`：40 / 40 passed

---

# 0. 最终目标

Qy 的目标不是“Python 上的一层 Lisp 语法”，而是：

- Python 实现的 like-Lisp 语言；
- 语言核心是：
  - everything is symbol；
  - syntax datum 只有 `symbol` 与不可变 `chain`；
  - 同一 symbol-space 内 symbol 不可重绑定；
  - algebraic effects；
  - register VM；
- 固定主管线：

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

- Python / Go 只是宿主与 adapter，不是语言语义本体；
- runtime value 是 Qy 语义对象，不能与 Python value 混淆；
- register VM 是唯一 runtime backend；
- 新能力默认先考虑能否由 Qy 自己实现，只有真正不可自举的能力才进入 host capability。

---

# 1. 不可漂移的语言契约

## 1.1 Syntax

- 语法只有 S-expression。
- raw AST / syntax datum 只能由：
  - `symbol`
  - immutable `chain` 构成。
- `form` 只是“一个 S-expression 单元”的叙述名，不是第三类语法对象。
- `chain` 不可变；`cons`、quasiquote、macro rewrite 都必须构造新 chain。
- `quote` 返回 syntax datum，不触发 runtime lookup。
- 默认 surface dialect 只做静态可描述的 spelling rewrite：
  - `'x -> (quote x)`
  - `` `x -> (quasiquote x)``
  - quasiquote 内 `,x -> (unquote x)`
  - quasiquote 内 `,@x -> (unquote-splicing x)`
- 不实现 unrestricted reader macro。

## 1.2 Runtime value

- runtime value 是 Qy 的语义对象。
- `nil` 与 `t` 是 Qy 自身对象。
- 抽象 runtime model 由：
  - `number`
  - `string`
  - `object` 构成；`number` 与 `string` 是特殊 object。
- Python value 只是宿主互操作对象，不能反向定义 Qy runtime model。
- host reference 是进入 Qy runtime 的语义对象；它可以指向 Python、Go 或其他宿主值。
- Python profile 可以显式暴露 `True` / `False` / `None` 等 Python value reference，但它们不等同于 `t` / `nil`。

## 1.3 Lookup 与 symbol-space

- 求值 symbol 时，沿 symbol-space-chain 顺序查找。
- `define`：
  - 只检查当前 symbol-space；
  - 构造一次性绑定；
  - 可以 shadow 后续链节点中的任意 symbol。
- `let`：
  - 新建局部 symbol-space；
  - 可以绑定任意 symbol。
- `pre-symbol-space-chain`：
  - 不是语言理想本身；
  - 但它是标准实现围绕 `Qy` 实例展开的起点事实；
  - reader、analyzer、LSP、lowering、runtime 必须读取同一实例事实。
- chain 只描述 lookup；
- fold 才会把 binding 吸收到目标 symbol-space；
- `from` 是受 `exports` 约束的选择性 fold；
- module root 初始化也必须使用同一 chain + fold 模型。

## 1.4 Core operators

- `quote`
- `atom eq car cdr cons`
- `define let cond`
- `pipeline parallel all race`
- `defun lambda apply`
- `macro quasiquote unquote unquote-splicing gensym capture`
- `defeffect perform handle resume`
- `module from import exports`

说明：

- `cond` 只把 `nil` 视为 false。
- `truthy` 是 standard profile 的复杂真值判断算子，不改变 `cond`。
- `pipeline` 表示串行。
- `parallel` 只表示允许并行，不要求并行；支持 effect。
- `all` 是 barrier continuation。
- `race` 是 first-resume-wins。

## 1.5 Read / Eval / Reify

- `read: stream -> syntax datum`
- `eval: syntax datum + symbol-space-chain -> runtime value`
- `reify: runtime value + target context -> syntax datum`
- `reify` 是 partial operation：
  - 默认只要求“再次求值后得到等价值”；
  - identity round-trip 必须显式依赖 binding / handle / context；
  - host reference 必须显式实现 reify，或 `perform` reify effect 交给 handler。
- `display` / `write` / `reify` / `eval` 不能混为一类。

## 1.6 Runtime identity

- `eq` 最终必须比较 Qy runtime identity。
- Qy 不能依赖 Python `id()` / `is` 定义语言 identity。
- 若提供用户可见 `id`，其稳定范围由 Qy runtime 定义，不得泄漏宿主地址语义。

---

# 2. 当前现状

## 2.1 已完成

- register VM 已成为唯一公开执行路径；
- `qy.ir_vm/` 与 `python_codegen.py` 已删除；
- `raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> VM` 主链已打通；
- `pipeline` / `parallel` / `all` / `race` / `apply` / effect 已进入主 pipeline；
- macroexpand 已独立，具备基础 hygiene、namespace、trace、source map；
- CLI 已支持：
  - `ast`
  - `expand`
  - `hir`
  - `mir`
  - `lir`
  - `bytecode`
- qytest 已形成一套行为验证集；
- examples 已分成 validation / design / host；
- `Environment.fold_from()` 已出现；
- `Qy.pre_symbol_space_chain` 已有只读快照；
- `evaluator.py` 已退出主求值路径。

## 2.2 仍在过渡

- raw AST 仍是 `Symbol | str | tuple[...]`，与目标 `symbol / immutable chain` 不一致；
- Python `str/int/list/tuple/dict/set/bool/None` 仍大量直接充当 runtime value；
- `eq` 仍由 Python `is` 支撑；
- `cond` / VM truthiness 仍受 Python 假值污染；
- `pre-symbol-space-chain` 仍更像展平 root + literal resolver；
- module / fold 存在多条近似实现路径；
- compile-time env 仍只是 runtime env facade；
- LIR 仍较薄，未完全承担低层职责；
- register VM 仍承担较多 host-call compatibility；
- `evaluator.py`、`eval_runtime.py`、legacy operator dispatch 仍活跃；
- `io`、`truthy`、`reify`、runtime identity 仍未落地。

## 2.3 当前主要事实漂移

1. `reader.Form` 仍允许 Python `str` 与 tuple；
2. quoted literal 已在 reader 阶段变成 Python `str`；
3. `values.py` 里的 runtime `QyChain` 与 syntax tuple 并存；
4. `literal_resolver` 让 `1` 等 spelling 绕过了真正的 chain / fold 模型；
5. `(define 1 10)` 的行为尚未由最终 root 模型解释；
6. `qy.core` 仍混入 profile / compat 能力；
7. `qy.stdlib.data` 仍把 Python 容器视为一等目标语义；
8. `eq` 仍受 Python interning 影响；
9. `cond` 仍把 `False` / `None` / `()` 当作 false；
10. `truthy` 仅在文档中存在，尚无正式 operator；
11. `io` 仍只是 `print/echo` 模块，不是 Qy runtime model；
12. `reify` 尚未实现；
13. `HostObjectRef` 尚未演化成完整 host reference / runtime identity 容器；
14. compile-time namespace 仍未真正与 runtime namespace 分离；
15. `from` 在 stdlib / VM / source-module 路径没有完全共用实现；
16. `quasiquote` nested 路径仍依赖过时 `list/append` 假设；
17. LIR 目前仍与 bytecode opcode 基本同构；
18. effect frame 仍主要由 VM 中的 Python 对象承担；
19. legacy `UserFunction` 仍让尾调用部分依赖旧 evaluator；
20. docs 中仍有少量旧说法需要持续清理。

---

# 3. 完成定义

只有同时满足以下条件，Qy 才算进入“架构闭合”状态：

- raw AST 真实只有 `symbol / chain`；
- runtime value 与 Python value 已严格分层；
- runtime identity 由 Qy 自己管理；
- `eq` / `cond` / `truthy` 按最新语义工作；
- `pre-symbol-space-chain` 是真实链，不是文档名词；
- `from` / module root / profile bootstrap 全部使用同一 fold primitive；
- macro 拥有真正 compile-time symbol-space；
- HIR / MIR / LIR 各自独立且有 verifier；
- LIR 已承担低层职责，bytecode compiler 只编码；
- register VM 不再依赖 legacy evaluator 承担核心语义；
- qytest 能覆盖语言契约；
- 文档、CLI、LSP、analyzer、runtime 读取同一事实源。

---

# 4. 完整推进路径

## Phase A. 文档与真源收口

### A1. 语言真源

- `LANGUAGE.md` 只描述稳定语言语义；
- `docs/op.md` 只描述 operator 分层与当前 operator 面；
- `docs/pipeline.md` 只描述阶段边界；
- `docs/ir-design.md` 只描述 HIR / MIR / LIR 的独立职责；
- `docs/stdlib-operators.md` 只描述可变 stdlib 草案；
- `docs/language-core-audit.md` 只描述实现偏移，不重复发明规范。

### A2. 说明文件一致性

- 保持以下文件同步：
  - `LANGUAGE.md`
  - `docs/op.md`
  - `docs/pipeline.md`
  - `docs/ir-design.md`
  - `docs/language-core-audit.md`
  - `AGENTS.md`
  - `CLAUDE.md`
  - `todo.md`
- 删除旧词：
  - `host value` 如果语义上指 runtime 对象，应改为 `host reference`
  - “Python 类型等于 Qy 类型”一类说法必须删除
  - 已移除的 backend / operator / form 不能残留

### A3. 报告制度

- 每批工作都写 `report.md`：
  - 目标；
  - 修改范围；
  - 新增 / 删除文件；
  - 复杂度变化；
  - 删除了哪些 legacy；
  - 引入了哪些新偏移；
  - 验证命令与结果。

---

## Phase B. Frontend：source -> raw AST -> surface dialect

### B1. raw AST 模型

- 把 raw AST 从 `Symbol | str | tuple` 收口为：
  - `Symbol`
  - immutable syntax `Chain`
- 删除 reader 阶段的 Python string 物化；
- 明确 syntax chain 与 runtime chain：
  - 是否同一数据结构；
  - 若不是，必须有严格边界与转换点；
  - 不允许长期存在“tuple AST + QyChain runtime”的混合模型。

### B2. literal spelling

- number / string / char spelling 在 raw AST 阶段仍只是 symbol 或受控 spelling；
- literal 解析只能发生在后续明确阶段；
- literal layer 必须属于 `pre-symbol-space-chain` 或显式 literal semantic pass，不能偷偷塞进 reader。

### B3. surface dialect

- 把 surface dialect 与 reader 本体真正拆开；
- 保留默认有限 sugar：
  - `'`
  - `` ` ``
  - `,`
  - `,@`
- binding / parameter 位置的 spelling rewrite 规则必须静态可知；
- analyzer、formatter、LSP、source map 共用同一 dialect 描述；
- 宿主可配置 dialect，但 Qy 源码不暴露 unrestricted reader macro。

### B4. source map / write / formatter

- `read_raw`、`surface dialect`、`macro expand` 都要保留可追踪 span；
- `write` 只处理 syntax datum，不承担 runtime `reify`；
- `display`、`write`、`reify` 的 API 与文档必须彻底拆开；
- formatter 只能操作 source/syntax 层，不得借 runtime 值判断。

### B5. 完成标准

- `qy ast` 输出只含 raw syntax model；
- raw AST 测试不再出现 Python `str` / tuple；
- reader、formatter、LSP 对同一 spelling 的理解一致；
- number/string spelling 的求值路径由实例链解释，而不是 reader 特判。

---

## Phase C. Runtime value / identity / truth / reify

### C1. runtime value 分层

- 建立 Qy runtime object model：
  - `nil`
  - `t`
  - `number`
  - `string`
  - `chain`
  - `object`
  - `host reference`
- 明确 Python `int/str/list/...` 只是实现或 adapter；
- 决定：
  - `number` / `string` 是否拥有 Qy wrapper；
  - 它们如何携带 runtime identity；
  - 何时允许零拷贝接宿主实现。

### C2. runtime identity

- 设计 Qy 自己的 identity：
  - 分配规则；
  - 生命周期；
  - GC / reuse 约束；
  - host reference 的 identity 绑定；
  - singleton identity；
  - 是否对值类型做 interning。
- `eq` 改为比较 Qy identity；
- 删除依赖 Python small-int interning 的测试与语义；
- 若提供 `id`：
  - 定义其返回值类型；
  - 定义稳定范围；
  - 明确它不等于 Python `id()`。

### C3. truth model

- `cond` 只把 `nil` 当 false；
- 修改：
  - lowering / MIR / VM branch 语义；
  - legacy evaluator；
  - stdlib control；
  - tests；
- 实现 `truthy`：
  - 它是 standard profile 的复杂判断 operator；
  - 由它自己判断 Python reference、容器、数值、数组等广义真值；
  - 它返回 `t` / `nil`；
  - 不引入全局 Python truth coercion。
- 决定 `if` / `for` / `while` 是否建立在 `truthy` 上，还是继续保持各自显式规则。

### C4. reify

- 定义三种强度：
  - 可求值表示；
  - 等价回环；
  - identity 回环；
- 默认契约采用等价回环；
- identity 回环只允许通过：
  - symbol binding；
  - module reference；
  - handle；
  - 显式 context；
- host reference：
  - 必须显式实现 reify；
  - 或 `perform` reify effect；
  - handler 负责导出引用、构造表达式或拒绝；
- 明确 `read` / `write` / `display` / `reify` / `eval` 的关系；
- 设计可供 LSP / debugger / REPL 使用的最小 reify 能力。

### C5. 完成标准

- `eq` 结果与 Python interning 无关；
- `cond` 的真假只由 `nil` 决定；
- `truthy` 成为显式 operator；
- Python value 不再直接充当规范中的 Qy value；
- `reify` 拥有最小实现与 failure protocol。

---

## Phase D. Symbol-space / profile / module / fold

### D1. pre-symbol-space-chain 真模型

- 把当前展平 root 拆成明确链节点：
  - writable head；
  - core profile；
  - literal layer；
  - standard profile；
  - optional stdlib layer；
  - host injection layer；
- 每个节点明确：
  - lookup 可见性；
  - local membership；
  - 是否可写；
  - 是否 lazy；
  - 是否会被 root fold；
- reader、analyzer、LSP、lowering、runtime 读取同一个实例事实。

### D2. define / shadow / fold

- 固定 root define 规则；
- 明确：
  - `(define 1 10)` 在默认 profile 下为何成功或失败；
  - 在 empty local symbol-space 中为何能 shadow；
- 把 module root 初始化、profile bootstrap、`from` 全部表达成 fold；
- fold 只吸收 export view，不复制 namespace 背后的隐含 fallback；
- 冲突规则统一：
  - 同层已有本地 binding -> fail；
  - parent / later chain -> 可 shadow；
  - alias 冲突 -> 按当前层 define-once。

### D3. module

- `module` = 具名 symbol-space；
- `exports` = export view；
- `from` = selective fold；
- `import` = 命名/alias 语法；
- 统一三条实现路径：
  - stdlib module path；
  - register VM path；
  - source module provisional path；
- 宏导出与 runtime 导出必须有一致模型；
- 明确模块初始化时：
  - profile chain；
  - local root；
  - exported macro；
  - re-export；
  - repeated import；的规则。

### D4. profile

- 固定分层：
  - core built-in；
  - standard profile；
  - optional stdlib；
  - host capability；
  - compat layer；
- arithmetic、truthy、io、chain convenience 等都要明确归属；
- `qy.core` 只保留真正核心；
- `qy.py` 继续保持显式 opt-in；
- CLI `operators`、analyzer、LSP、runtime 使用同一 profile 描述。

### D5. 完成标准

- 同一 `Qy` 实例下，lookup / analyzer / LSP / runtime 全部一致；
- module / from / profile bootstrap 只剩一套 fold primitive；
- profile 差异可测试、可 introspect、可序列化说明。

---

## Phase E. Operator system

### E1. operator 分层

- core operator；
- standard built-in；
- optional stdlib operator；
- host capability operator；
- compat operator；
- 文档、metadata、runtime 三方一致。

### E2. operator metadata

- 固定 operator declaration schema：
  - name；
  - layer；
  - arity；
  - argument policy；
  - argument types；
  - rest type；
  - return type；
  - effects；
  - compile-time；
  - runtime-meta；
  - tail transparency；
  - docs；
  - source module / profile visibility；
- analyzer、LSP、CLI docs、lowering、runtime 统一读取；
- 不再让 `CORE_OPERATOR_SIGNATURES` / `STDLIB_OPERATOR_SIGNATURES` / 真实导出集合互相漂移。

### E3. custom operator

- 用户自定义 operator 必须能提供声明；
- 声明完整时：
  - analyzer 可做 arity / type / effect 检查；
  - LSP 可做 hover / completion / diagnostics；
  - lowering 可正确决定 argument policy；
- 声明不完整时：
  - 显式退化为 `unknown/any`；
  - 工具链不得从 Python 实现细节臆测语义。

### E4. core cleanup

- `qy.core` 只保留核心语义；
- `chain/append/get/has?/len/type/is` 等必须重新归层；
- `eval` 的层级必须重新确认：
  - 若它仍是 standard / meta 能力，不能偷留在 core；
  - 若它要进入 core，需要在 `LANGUAGE.md` 明确；
- `spawn` / `await` 保持移除；
- `defer` 保持移除，除非未来作为单独 meta/control 设计重开。

### E5. 完成标准

- 一个 operator 的语义只在一个声明源中定义；
- `operators` CLI 与 analyzer / runtime 输出一致；
- 自定义 operator 可以被 LSP 正确理解。

---

## Phase F. Macro system

### F1. compile-time symbol-space

- `compile_time_environment()` 不再只是 runtime env facade；
- 独立建模：
  - definition-site binding；
  - compile-time profile；
  - allowed capability；
  - effect policy；
  - module macro import/export；
- runtime namespace 不得无控制泄漏到 macro namespace。

### F2. hygiene

- 保持默认 hygienic；
- `capture` 作为唯一 intentional capture 路径；
- `gensym` 使用独立 identity；
- source map 必须可把展开结果追回：
  - call site；
  - definition site；
  - rename；
  - generated symbol。

### F3. quasiquote

- nested quasiquote 不得依赖过时 `list/append` 假设；
- quasiquote / unquote / unquote-splicing 的 lowering 只依赖稳定 core 面；
- macro 与 surface dialect 的责任严格分离。

### F4. diagnostics / tools

- expansion trace 可供：
  - CLI；
  - LSP；
  - diagnostics；
  - debugger；
- macro failure 必须带 compile-time stack 与 source map；
- qytest 覆盖：
  - hygiene；
  - capture；
  - gensym；
  - module macro import；
  - expansion failure；
  - source map。

### F5. 完成标准

- macro 不借 runtime env “顺手可用”；
- compile-time effect policy 可解释；
- hygiene 与 capture 可被 tools 正确展示。

---

## Phase G. HIR

完整要求见 `docs/ir-design.md`。这里列推进任务。

### G1. HIR 定位

- HIR 是 **高层语义 IR**；
- 它必须独立于：
  - surface dialect spelling；
  - raw AST 表示；
  - MIR CFG；
  - register VM；
  - Python host object layout。

### G2. HIR 必须表达

- resolved binding；
- symbol-space 语义；
- operator declaration / signature；
- structured control；
- function / lambda；
- effect；
- module / fold；
- macro definition payload（仅在语义需要时携带 syntax datum）；
- source span；
- diagnostics；
- type/effect facts；
- tail-position facts；
- unresolved symbol as explicit node。

### G3. HIR 必须禁止

- raw tuple AST 泄漏；
- runtime `Environment` 对象引用；
- Python host value 直接作为语义；
- bytecode opcode；
- physical register；
- jump offset；
- hidden reliance on legacy `raw_args` compatibility。

### G4. HIR 需要补齐

- `BindingId` / stable binding reference；
- profile-aware resolved symbol info；
- runtime identity-independent literal representation；
- effect signature facts；
- operator declaration ref；
- verifier；
- dump 稳定格式；
- HIR-level tests；
- 删除 legacy `raw_args`；
- 明确 `eval`、`truthy`、future standard control 的 HIR 归属。

### G5. HIR 完成标准

- 给定 macroexpanded syntax + `Qy` instance facts，HIR 是确定的；
- HIR 不依赖 VM 就能被 analyzer / LSP 消费；
- HIR verifier 能拒绝：
  - 未声明但被当成 resolved 的 binding；
  - 非法 structured node；
  - 缺失 signature；
  - invalid span / effect facts。

---

## Phase H. MIR

### H1. MIR 定位

- MIR 是 **控制流与虚拟寄存器 IR**；
- 它必须独立于：
  - source spelling；
  - raw AST；
  - HIR 的树形便利；
  - physical register layout；
  - bytecode encoding；
  - host ABI。

### H2. MIR 必须表达

- CFG；
- basic block；
- virtual register；
- explicit evaluation order；
- branch / jump / return / tail call terminator；
- scope entry / exit；
- call；
- effect perform / handle / resume；
- ordering/join semantics；
- module / fold operation；
- constant / binding references；
- source debug metadata。

### H3. MIR 必须禁止

- Environment lookup；
- runtime Python value 作为随意 payload；
- bytecode opcode 同构假设；
- physical register；
- final jump offset；
- structured control 仍以 HIR node 偷留；
- compile-time macro semantics。

### H4. MIR 需要补齐

- 真正的 constant reference / pool model，替代 `LOAD_HOST` 直接塞 Python object；
- explicit effect edges / handler regions；
- resume continuation 结构；
- scope lifetime model；
- call convention abstract form；
- def-use verifier；
- CFG verifier；
- reachability；
- register liveness；
- tail-call verifier；
- dominance / ownership 规则（即使不采用 SSA，也要有明确 register 定义约束）；
- MIR pass pipeline：
  - canonicalize；
  - CFG simplify；
  - dead block cleanup；
  - constant / copy propagation（在 runtime model 稳定后）；
  - tail-position preservation。

### H5. MIR 完成标准

- HIR 的 structured semantics 已全部显式化为 MIR 控制流；
- MIR lowering 不依赖 Environment；
- MIR verifier 能独立发现非法 CFG、非法寄存器使用、非法 effect region；
- MIR dump 可直接解释程序控制流，不需要回看 HIR。

---

## Phase I. LIR

### I1. LIR 定位

- LIR 是 **低层、VM-facing、但尚未编码的 IR**；
- 它必须独立于：
  - HIR；
  - MIR tree / CFG 结构；
  - bytecode binary/encoding 细节；
- 它不能再只是“共享 bytecode opcode 的线性 MIR”。

### I2. LIR 必须表达

- instruction selection 后的低层指令；
- scheduled / linearized block order；
- physical register layout 或明确 frame slot layout；
- calling convention；
- effect frame layout；
- continuation layout；
- host-call ABI lowering；
- relocatable jump target / fixup；
- debug span / trace injection；
- constant pool reference；
- frame metadata；
- stack-map / continuation-map（若后续 GC / debugger 需要）。

### I3. LIR 必须禁止

- HIR node；
- MIR block semantic 依赖；
- Environment；
- source-level binding lookup；
- bytecode compiler 再次做高层决策；
- 与 bytecode opcode 一比一绑定到无法重写的程度。

### I4. LIR 需要补齐

- 自己的 opcode vocabulary；
- selection pass；
- block layout / rerank；
- register allocation / compaction；
- effect frame lowering；
- host ABI lowering；
- jump fixup；
- peephole；
- debug injection；
- verifier；
- textual dump；
- LIR pass ordering；
- LIR 与 bytecode 之间的 relocation / encoding boundary。

### I5. LIR 完成标准

- `LIR -> bytecode` 只剩 encode / pack / relocate；
- effect frame 不再主要依赖 VM Python closure；
- host-call ABI 已在 LIR 层明确；
- 所有低层 rewrite 都能说清属于哪一个 LIR pass；
- LIR 可以为了不同 register VM 版本调整，而不需要回改 HIR / MIR。

---

## Phase J. Bytecode

### J1. bytecode 定位

- bytecode 是 register VM 的最终可执行表示；
- 它只消费 LIR；
- 它不重新理解：
  - binding；
  - effect；
  - module；
  - control；
  - profile；
  - host semantics。

### J2. 需要完成

- constant pool；
- function table；
- debug table；
- source map table；
- relocation 已闭合；
- validation；
- optional serialization format；
- versioning / compatibility strategy；
- bytecode dumper；
- round-trip test；
- invalid bytecode rejection。

### J3. 完成标准

- bytecode compiler 是结构转换器，不再含高层语义；
- register VM 可只看 bytecode 执行；
- bytecode dump 能与 LIR 对照验证。

---

## Phase K. Register VM

### K1. VM 定位

- 唯一执行器；
- 执行 bytecode；
- 不承担语言前端；
- 不承担 macro；
- 不承担 HIR/MIR 语义修补。

### K2. 必须完成

- 真 register execution；
- Qy runtime identity；
- frame layout；
- function call；
- tail call；
- continuation；
- effect frame；
- `pipeline` / `parallel` / `all` / `race`；
- module / fold runtime operations；
- host-call ABI；
- error stack；
- debugger hooks；
- profiler hooks；
- GC / lifetime hooks（若对象模型需要）。

### K3. 当前需要迁移

- `_truthy` 改为 `nil` only；
- `_EffectFrame` 从 Python runtime detail 下沉到 LIR/bytecode model；
- host-call compatibility 缩到 adapter 层；
- `parallel` / `all` / `race` 的 continuation 与取消规则固定；
- mutual recursion TCO；
- effect boundary TCO；
- Python call stack 完全退出语义依赖；
- `UserFunction` 迁到 bytecode function；
- legacy operator dispatch 退出 core semantics。

### K4. 完成标准

- 新增核心语义不需要修改 evaluator；
- effect + tail call + parallel/join 能只从 bytecode 解释；
- VM 运行结果不依赖 Python interning / truthiness / callable semantics。

---

## Phase L. Legacy removal

### L1. evaluator

- `evaluator.py` 只能继续减，不能新增语义；
- 移除：
  - tail body path；
  - old effect continuation composition；
  - legacy truthiness；
  - compatibility exports；
- `eval_runtime.py` 最终降为零职责或删除。

### L2. legacy operator dispatch

- `PureOperator` / `ScopeOperator` / `ControlOperator` / `EffectOperator` / `MetaOperator` 最终只能保留为 host adapter，如无必要则删除；
- core semantics 全部走正式 IR / VM；
- stdlib 不再依赖 argument evaluator hack。

### L3. compat modules

- `qy.legacy` 仅用于迁移期；
- `spawn` / `await` / `component` 等不回流 core；
- 旧 `str-*` family 删除；
- 过渡 examples / tests 删除或迁到 compat test。

### L4. 完成标准

- 搜索 `qy.evaluator` 只剩历史文档或不存在；
- 新增 operator 不需要在 evaluator 与 VM 写两遍；
- legacy docs 完全隔离。

---

## Phase M. Standard profile / stdlib / host capability

### M1. standard profile

- 明确默认预装：
  - 哪些 core；
  - 哪些 standard built-in；
  - 哪些 literal layer；
  - 哪些 host capability；
- 默认 profile 不等于语言核；
- profile 可被实例化配置覆盖。

### M2. number

- 决定 number runtime model；
- 完成 `qy.num`：
  - host primitive；
  - Qy library；
  - equality；
  - comparison；
  - numeric tower；
  - numpy 互操作边界；
- arithmetic 是否默认加载必须由 profile 明确。

### M3. string

- 删除旧 `str-*`；
- 完成 `qy.str`：
  - runtime `string`；
  - host primitive；
  - Qy library；
  - Unicode policy；
  - string equality；
  - formatter / writer / display 分离。

### M4. io / fs / process / network

- `io` 是 Qy 自己的 runtime model，不是 Python file object 的别名；
- 先定义：
  - input stream；
  - output stream；
  - bidirectional stream；
  - byte stream；
  - char stream；
- 再定义 minimal capability：
  - read；
  - write；
  - flush；
  - close；
  - maybe seek；
- 分离：
  - `io`
  - `fs`
  - `process`
  - `network`
- Python / Go 只做 adapter；
- `echo` 若保留，应只是基于 `io` 的便利算子；
- 明确哪些 I/O 操作走 effect。

### M5. containers / object / struct

- 决定 list / tuple / set / dict / struct / object 的 Qy 语义；
- 若它们只是 host adapter，不得伪装成语言基本类型；
- 若它们是正式 runtime family，必须：
  - 有 identity；
  - 有 type model；
  - 有 reify；
  - 有 operator family；
  - 有 analyzer support。

### M6. 完成标准

- standard profile 足够可用；
- stdlib 不是 Python helper 的随机集合；
- 宿主生态通过 adapter 进入，不反向决定语言结构。

---

## Phase N. Analyzer / LSP / CLI / formatter / tooling

### N1. analyzer

- 读取实例 profile / symbol-space-chain；
- 消费统一 operator declaration；
- 消费 HIR binding / type / effect facts；
- 支持：
  - unresolved symbol；
  - duplicate define；
  - arity；
  - type；
  - effect declaration；
  - module export/import；
  - macro diagnostics；
  - profile-specific symbols；
- 不自己发明 runtime truth 或 host type 规则。

### N2. LSP

- 基于具体 `Qy` 实例；
- completion / hover / diagnostics / rename 读取同一 metadata；
- 展示：
  - macro expansion；
  - hygiene rename；
  - source map；
  - operator signature；
  - module export；
  - profile visibility；
- 不把 Python 实现细节显示成 Qy 语义。

### N3. CLI

- 保持：
  - `ast`
  - `expand`
  - `hir`
  - `mir`
  - `lir`
  - `bytecode`
- 后续增加：
  - profile dump；
  - symbol-space-chain dump；
  - module export dump；
  - operator declaration dump；
  - macro trace；
  - maybe reify/debug tools。

### N4. formatter

- 只围绕 syntax；
- 与 surface dialect 同源；
- 不偷偷 normalize runtime value；
- 能 round-trip raw AST。

### N5. 完成标准

- analyzer / LSP / CLI / runtime 对同一实例的事实一致；
- 调试工具能观察每一层，不需要读 Python 源码猜。

---

## Phase O. Testing / examples / benchmarks

### O1. 测试分层

- `pytest`
  - 验证 Python 实现；
  - 验证每一编译层；
  - 验证 diagnostics；
  - 验证 regression；
- `qy test.qy tests/qy`
  - 验证语言行为契约；
  - 由 Qy 自己描述语言案例。

### O2. qytest

- 保持 host capability 最小：
  - read file；
  - list dir；
  - path；
  - args；
- assertion / reporting / DSL 尽量由 Qy 自举；
- 新增行为集：
  - raw AST；
  - nil-only cond；
  - truthy；
  - runtime identity；
  - reify；
  - profile；
  - pre-symbol-space-chain；
  - fold；
  - macro failure；
  - compile-time env；
  - io；
  - module conflict；
  - effect + parallel/race/all。

### O3. stage tests

- reader；
- surface dialect；
- macroexpand；
- HIR verifier；
- MIR verifier；
- LIR verifier；
- bytecode verifier；
- VM execution；
- analyzer；
- LSP；
- CLI；
- formatter；
- profile snapshot。

### O4. examples

- `validation/` 只保留当前可运行契约；
- `design/` 只描述未来目标；
- `host/` 展示 adapter 与 embedding；
- 删除解释旧实现的样例。

### O5. benchmarks

- 只保留 register VM 维度；
- workload 至少覆盖：
  - arithmetic；
  - recursion；
  - tail recursion；
  - module import；
  - macro heavy；
  - effect heavy；
  - string；
  - parallel/join；
- 记录：
  - parse；
  - surface；
  - expand；
  - HIR；
  - MIR；
  - LIR；
  - bytecode；
  - VM；
- 增加：
  - historical baseline；
  - regression threshold；
  - optional CI gate。

### O6. 完成标准

- 语言契约变化先改 qytest；
- 每一阶段有独立测试；
- benchmark 能解释性能回退来自哪个阶段。

---

## Phase P. Performance / optimization / diagnostics

### P1. front-end

- 缓存 source read / expand / lower；
- 避免重复全链路工作；
- macro cache；
- module cache；
- source map 成本监控。

### P2. HIR / MIR / LIR

- HIR：
  - binding pre-resolution；
  - constant binding fact；
  - effect fact；
- MIR：
  - CFG simplify；
  - dead block；
  - tail-call canonicalization；
  - liveness；
- LIR：
  - layout；
  - allocation；
  - rerank；
  - peephole；
  - debug injection switch；
- 所有优化必须能证明不越层。

### P3. VM

- frame allocation；
- environment allocation；
- tail-call frame reuse；
- continuation capture cost；
- host-call ABI；
- parallel scheduling cost；
- runtime identity allocation；
- constant pool。

### P4. diagnostics

- 每层错误都带 span；
- macro trace；
- virtual stack；
- effect stack；
- module path；
- profile info；
- source map；
- debugger 可解释 LIR / bytecode。

---

## Phase Q. Embedding / packaging / portability

### Q1. Qy instance API

- 自定义 profile；
- 注入 symbol-space-chain；
- 注册 custom operator；
- 注册 host reference adapter；
- 配置 surface dialect；
- 配置 macro capability；
- 配置 I/O / FS / process capability。

### Q2. portability

- Python backend 是当前实现；
- 语言模型不得依赖 Python：
  - truthiness；
  - identity；
  - object layout；
  - exception hierarchy；
  - file object；
- Go adapter / other host adapter 必须能复用同一 runtime model。

### Q3. packaging

- CLI；
- library API；
- VS Code extension；
- documentation；
- versioned bytecode；
- stdlib packaging；
- profile packaging。

---

# 5. 依赖顺序

以下顺序不建议打乱：

1. raw AST / syntax model；
2. runtime value / Python value 边界；
3. runtime identity + `eq` + `cond` + `truthy`；
4. pre-symbol-space-chain / profile / fold；
5. operator declaration；
6. macro compile-time env；
7. module path 统一；
8. HIR 收口；
9. MIR 收口；
10. LIR 真正独立；
11. VM effect frame / TCO；
12. legacy 删除；
13. stdlib / io / fs 扩张；
14. 性能优化与 portability。

原因：

- syntax 与 runtime model 不稳，后续 IR 会反复返工；
- symbol-space 不稳，analyzer / LSP / module / macro 都会漂；
- HIR 不稳，MIR/LIR 细化会建立在旧语义上；
- LIR 不独立，bytecode 与 VM 会继续吞掉本应属于 lowering 的职责。

---

# 6. 复杂度控制

当前冻结增长文件：

- `qy/lowering.py`
- `qy/analyzer.py`
- `qy/register_vm.py`
- `qy/mir.py`
- `qy/macroexpand.py`
- `qy/macro_hygiene.py`
- `qy/reader.py`
- `qy/evaluator.py`

规则：

- `evaluator.py` 只能减，不能加；
- 新语义不能同时落到 evaluator 与 VM 两套路径；
- 先拆真实边界，再加新分支；
- 新模块必须对应稳定概念，不得只搬运复杂度；
- 任何新增 host operator 都要回答：
  - 能否由 Qy 自己实现？
  - 属于 core / profile / stdlib / host capability 哪层？
  - metadata 是否完整？
  - 是否可被 analyzer / LSP 理解？

---

# 7. 删除清单

已删除：

- `qy.ir_vm/`
- `python_codegen.py`

必须继续删除或降级：

- `evaluator.py` 的剩余真实职责；
- `eval_runtime.py` 兼容面；
- legacy operator dispatch 对 core semantics 的承担；
- old `str-*`；
- `qy.legacy` 依赖；
- Python 容器伪装成语言核心类型的路径；
- Python `is` / truthiness 泄漏进语言语义的路径；
- 只验证旧过渡实现的 tests / examples；
- 与最新语言设计冲突的文档残留。

---

# 8. 验证矩阵

## 每批默认

```bash
uv run python -m pytest -q
uv run ty check .
uv run python -m qy test.qy tests/qy
```

## 触碰 frontend

```bash
uv run python -m pytest tests/test_reader_forms.py tests/test_reader_symbols.py tests/test_reader_write.py tests/test_formatter.py -q
```

## 触碰 macro

```bash
uv run python -m pytest tests/test_eval_macro.py tests/test_macroexpand.py tests/test_module_import.py -q
```

## 触碰 HIR / analyzer

```bash
uv run python -m pytest tests/test_ir.py tests/test_hir_nodes.py tests/test_analyzer_basic.py tests/test_analyzer_scope.py tests/test_analyzer_advanced.py -q
```

## 触碰 MIR / LIR / bytecode / VM

```bash
uv run python -m pytest tests/test_mir.py tests/test_lir.py tests/test_register_vm.py tests/test_register_vm_semantics.py tests/test_runtime.py -q
```

## 触碰 module / profile

```bash
uv run python -m pytest tests/test_environment.py tests/test_scope.py tests/test_module_import.py tests/test_binding_consistency.py tests/test_operator_signature.py -q
```

## 触碰 tooling

```bash
uv run python -m pytest tests/test_cli_commands.py tests/test_lsp.py tests/test_formatter.py -q
```

---

# 9. 近期执行序列

尽管本文件写的是完整路线，最近几批仍应按以下顺序推进：

1. **frontend 收口**
   - raw AST 改回 symbol / chain；
   - surface dialect 从 reader 中拆出；
   - writer / formatter 同步。
2. **runtime model 收口**
   - runtime value / Python value 分层；
   - Qy identity；
   - `eq`；
   - `cond`；
   - `truthy`。
3. **symbol-space 收口**
   - pre-symbol-space-chain 真模型；
   - fold / module / profile 统一。
4. **IR 文档落地为实现**
   - HIR binding ref；
   - MIR constant / effect region；
   - LIR 独立 opcode 与 low-level pass。
5. **legacy 清除**
   - `UserFunction` -> bytecode function；
   - evaluator 退场；
   - compat stdlib 下沉。

---

# 10. 结束条件

项目进入下一阶段前，至少应达到：

- 文档与实现不再分别描述两个语言；
- runtime object model 不再依赖 Python 偶然性质；
- IR 三层各自可独立解释、验证、演进；
- evaluator 不再承担核心语义；
- qytest 成为语言行为验收面；
- register VM 可以被视为真正唯一后端，而不是“主路径 + 旧解释器阴影”。
