# Qy IR Design

本文档定义 HIR、MIR、LIR 的独立职责。三者不是“同一棵树的三种打印格式”，而是三个不同抽象层；每一层都必须有自己稳定的输入、输出、禁止事项、verifier 与演进空间。

---

# 1. 总原则

```text
macroexpanded syntax datum
  -> HIR
  -> MIR
  -> LIR
  -> bytecode
```

- HIR 负责**高层语义**；
- MIR 负责**控制流与虚拟寄存器**；
- LIR 负责**Qy abstract machine lowering**；
- bytecode 只负责**最终编码与执行输入**。

## 1.1 层间约束

- 上一层的便利结构不能偷偷穿透到下一层；
- 下一层的实现细节不能反向污染上一层；
- 每层都必须可单独 dump、verify、test；
- 任何 rewrite 都必须能回答“它唯一属于哪一层”；
- 如果某个变换必须同时理解两个层级，说明边界还没有切好。

## 1.2 连续算子（continuous operator）

某些算子在 IR 层面是**不可中断点**：它们的求值必须以一个原子段出现，pass 不得在该段内部插入 terminator、分支、scope 切换或 effect-region 边界。这类算子被称为**连续算子**。

- 连续性是一项**算子签名事实**，由 `OperatorSignature.continuous` 声明，并在 HIR 的 `Binding` / `BindingRef` / `CallExpr` 上传播。
- MIR 与 LIR 的指令携带 `continuous: bool` 标志；它由对应 HIR call lowering 而来，不是新 opcode。
- 三层 verifier 都对连续段做结构校验：
  - 连续指令本身不得是 break-point opcode；
  - 连续指令在同一 block / 线性流中前后相邻位置不得出现 break-point opcode；
  - 连续段不得跨 block 拆分。
- "break-point opcode" 是 pass 视角下会割裂控制流或切换执行环境的 opcode，例如 `ENTER_SCOPE` / `EXIT_SCOPE` / `HANDLE` / `PERFORM` / `RESUME` / `CACHE_EVAL` / `RUNTIME_EVAL` / 各 join opcode；LIR 还包括 `SS_ENTER` / `SS_LEAVE` / `FRAME_ENTER` / `FRAME_LEAVE` / `HANDLER_PUSH` / `HANDLER_POP` 等。
- 连续算子典型来源是宿主提供的纯计算操作（`cons` / `car` / `cdr` / `eq` / `+` / `-` 等）；它们由 VM 一次性执行完毕，pass 没有理由在其中插入控制流。

连续性不是优化提示，而是一项静态结构不变量；任何 pass 引入的 rewrite 必须保留连续段的不可分裂性，否则 verifier 直接报错。

---

# 2. HIR

## 2.1 定位

HIR 是 **高层语义 IR**。

它回答：

- 这个表达式语义上是什么？
- 它绑定到哪个 symbol-space binding？
- 它是哪类 operator / function / effect / module construct？
- 哪些控制结构必须保留为结构化节点？
- 哪些事实已经能被静态分析？

它不回答：

- 最后怎么跳转；
- 用几个寄存器；
- 怎么编码；
- register VM 怎么执行。

## 2.2 输入 / 输出

- 输入：
  - macroexpanded syntax datum；
  - 当前 `Qy` 实例的静态事实：
    - profile；
    - symbol-space-chain；
    - operator declaration；
    - module visibility；
- 输出：
  - `ProgramHIR`；
  - diagnostics；
  - 稳定的 binding / type / effect facts。

当前代码中的 `ProgramIR` 可视为过渡 HIR；后续应明确命名与边界。

## 2.3 HIR 必须保留的结构

- literal / syntax payload；
- resolved symbol ref；
- unresolved symbol ref；
- `quote`；
- `define`；
- `let`；
- `cond`；
- `lambda` / `defun` / `apply`；
- `pipeline` / `parallel` / `all` / `race`；
- `defeffect` / `perform` / `handle` / `resume`；
- `module` / `from` / `exports`；
- `macro` declaration payload；
- source span；
- diagnostics；
- tail-position fact；
- operator declaration ref；
- binding ref；
- type/effect fact。

说明：

- 只有真正改变 binding、evaluation order、control、effect、module 语义的构造，才值得拥有 HIR node；
- 纯便利算子不应因为“常用”就进入 HIR special node；
- 当语义需要保留 syntax datum 时，例如 `quote` 或 macro declaration body，HIR 可以携带 syntax payload，但必须显式标注为 syntax payload，而不是混成普通 runtime value。

## 2.4 HIR 必须禁止

- raw tuple AST；
- surface dialect spelling；
- Python host value 作为语言事实；
- runtime `Environment`；
- physical register；
- basic block；
- jump offset；
- bytecode opcode；
- VM frame layout；
- 依赖 legacy operator `raw_args` 的长期语义。

## 2.5 HIR 需要的核心数据

### BindingRef

HIR 中的 resolved symbol 不应只保存裸名字，应逐步迁到稳定 binding address。这里必须区分：

- syntax symbol：源码 / datum 层的符号拼写；
- binding address / slot：某个 symbol-space 中的稳定地址；
- runtime value：binding 完成后的值。

BindingRef 至少包含：

- stable binding id；
- symbol；
- binding source；
- owner symbol-space；
- slot state fact（declared / pending / completed 的静态近似）；
- resolved type；
- operator declaration ref；
- optional constant value ref。

`define` 只提升 binding，不提升 RHS 求值。HIR 必须能表达“当前 symbol-space 已经拥有该 binding，但该 binding 在运行到对应 `define` RHS 前可能仍是 pending value”。这不是 unresolved symbol，也不是提前求值。

### OperatorRef

HIR 不能只靠字符串再去查 signature；应引用统一 operator declaration。

### EffectRef

`perform` / `handle` 应引用已解析 effect declaration，至少携带：

- effect name；
- resumable；
- visibility；
- declaration span。

### ModuleRef

module import / export 应明确：

- module identity；
- export view；
- alias；
- fold destination。

## 2.6 HIR verifier

至少检查：

- 所有 resolved symbol 都有合法 `BindingRef`；
- unresolved symbol 不被伪装成 resolved；
- special node arity 合法；
- `handle` / `resume` / `perform` 的 effect facts 完整；
- module import/export facts 完整；
- tail-position 标记只出现在允许位置；
- syntax payload 只出现在允许节点；
- direct definition hoist 后同层 binding 无重复；
- pending binding read 拥有明确 effort / diagnostic policy；
- node type/effect facts 与 operator declaration 不矛盾。

## 2.7 HIR pass

允许：

- binding normalization；
- structured semantic normalization；
- constant binding folding（在 identity / reify 语义允许时）；
- type/effect fact propagation；
- invalid-node diagnostics。

禁止：

- CFG flatten；
- register assignment；
- host ABI lowering；
- bytecode selection；
- effect frame layout。

## 2.8 HIR 完成标准

- analyzer / LSP 可直接消费 HIR facts；
- 给定相同 macroexpanded syntax + `Qy` instance facts，HIR 结果确定；
- dump HIR 时，不需要读 Python runtime 对象才能理解语义；
- HIR 可独立通过 verifier。

---

# 3. MIR

## 3.1 定位

MIR 是 **控制流与虚拟寄存器 IR**。

它回答：

- 程序按照什么控制流执行？
- 哪些值流入哪些后续计算？
- 哪些分支、尾调用、effect、join 是显式控制边？

它不回答：

- 最终物理寄存器是多少；
- bytecode 如何编码；
- host call ABI 是什么；
- source spelling 是什么。

## 3.2 输入 / 输出

- 输入：
  - verified HIR；
- 输出：
  - `MIRProgram`；
  - CFG；
  - virtual register graph；
  - diagnostics。

## 3.3 MIR 必须表达

- function；
- basic block；
- explicit terminator；
- virtual register；
- branch；
- jump；
- return；
- tail call；
- scope enter / exit；
- call；
- apply；
- module define / from import；
- perform / handle / resume；
- parallel / all / race；
- constant ref；
- binding ref；
- binding slot read / complete；
- pending-binding edge / effort；
- symbol-space-chain transition；
- source debug metadata。

## 3.4 MIR 必须禁止

- raw AST；
- surface dialect；
- HIR structured control 留壳；
- runtime `Environment` lookup；
- physical register；
- bytecode offset；
- final host ABI；
- arbitrary Python object payload；
- compile-time macro semantics。

## 3.5 控制流要求

- 每个 block 必须且只能有一个 terminator；
- tail call 必须是 terminator，不是普通 instruction；
- branch 必须显式列出 true / false successor；
- effect control flow 必须逐步显式化：
  - handler region / marker；
  - perform edge；
  - resume edge；
  - non-resumable exit；
  - symbol-space-chain transition；
- `parallel` / `all` / `race` 的 join 规则必须在 MIR 中可解释，而不是留到 VM 猜测。
- MIR 可以保留 `handle` 作为 effect region / marker 的语义边界，但必须让 perform/resume 的控制边可见；到 LIR 边界时，语言级 `handle` / `perform` / `resume` 必须被消除。

## 3.6 虚拟寄存器要求

- virtual register 必须有明确 def / use；
- 即使不采用 SSA，也要定义：
  - 一个寄存器何时可重定义；
  - 跨 block 传递如何表达；
  - branch merge 如何表达；
- 后续若引入 phi / block parameter，要作为 MIR 规则，不可在 LIR 才补。

## 3.7 常量与绑定

- `LOAD_HOST` 这种“直接塞 Python 对象”的过渡 opcode 应替换为：
  - constant ref；
  - host reference ref；
  - binding ref；
- MIR 只携带语义引用，不携带宿主偶然表示。

## 3.8 MIR verifier

至少检查：

- main function index；
- block id 唯一；
- entry block 存在；
- block terminator 存在；
- successor 合法；
- register def/use 合法；
- operand kind 合法；
- terminator / instruction 分类合法；
- tail call 位置合法；
- effect region / resume edge 合法；
- unreachable block；
- scope enter / exit 配对；
- join 操作语义完整。

## 3.9 MIR pass

允许：

- structured control lowering；
- CFG simplification；
- dead block elimination；
- constant propagation（当 runtime model 允许）；
- copy propagation；
- tail-call canonicalization；
- effect-region normalization；
- join normalization。

禁止：

- physical register allocation；
- bytecode opcode selection；
- final jump fixup；
- host ABI lowering；
- debug bytecode injection。

## 3.10 MIR 完成标准

- 只看 MIR dump 就能解释程序控制流；
- MIR lowering 不访问 `Environment`；
- 所有 structured HIR control 都已变成显式 CFG；
- MIR verifier 能独立拦住非法程序。

---

# 4. LIR

## 4.1 定位

LIR 是 **Qy abstract machine IR**：低层、VM-facing、尚未最终编码，但已经把 Qy 语言执行机制完全显式化。

它回答：

- virtual stack 如何表示？
- continuation frame 如何捕获、复制、恢复？
- handler frame / effect marker 如何布局？
- symbol-space-chain 如何 enter / leave / copy / restore？
- binding slot 如何 lookup / read / complete / report pending？
- MIR 的 effect edge 如何变成 CFG jump + ss-chain transition？
- 物理寄存器 / frame / continuation / host ABI 怎么布局？
- 哪些 fixup、peephole、debug 注入应该在编码前完成？

它不回答：

- source-level binding 是什么；
- macro 是什么；
- HIR structured semantics 是什么；
- bytecode 的最终二进制或序列化格式是什么。

简述：

```text
MIR 描述程序控制流；
LIR 描述 Qy 抽象机器如何执行这些控制流。
```

当前实现允许两个 LIR dialect：

- `compat`：迁移期 LIR，仍可携带部分旧 bytecode-like opcode，用于保持现有 register VM pipeline 可运行；
- `abstract-machine`：目标 LIR，禁止语言级 `handle` / `perform` / `resume` 留壳，必须显式表达 frame、continuation、handler、ss-chain、lookup、slot operation。

新语义只能向 `abstract-machine` dialect 收口；`compat` 只能减少，不能扩张。

## 4.2 输入 / 输出

- 输入：
  - verified MIR；
- 输出：
  - verified LIR；
  - linear instruction stream；
  - physical layout metadata；
  - relocation / fixup metadata；
  - debug metadata。

## 4.3 LIR 必须表达

- selected low-level instruction；
- linearized block order；
- physical register 或 frame slot；
- calling convention；
- frame layout；
- virtual stack frame；
- continuation frame；
- handler frame / effect marker；
- continuation capture / copy / restore；
- symbol-space-chain enter / leave / copy / restore；
- lookup operation；
- binding slot read / complete / pending effort；
- CFG space transition；
- effect dispatch / unwind 的低层控制流；
- host-call ABI；
- jump target / relocation；
- constant pool ref；
- debug span；
- trace hook；
- stack / continuation map（若 runtime 需要）。

## 4.4 LIR 必须禁止

- HIR node；
- MIR block semantic 依赖；
- source-level name lookup（LIR 只能保留已 lower 的 symbol-space lookup operation）；
- 语言级 `handle` / `perform` / `resume` 留壳；
- `Environment`；
- compile-time semantics；
- bytecode compiler 回头再决定高层语义；
- 与 bytecode opcode 完全同构到无法重写。

## 4.5 LIR pass pipeline

建议至少拆成：

1. instruction selection；
2. block scheduling / layout；
3. register allocation / compaction；
4. call ABI lowering；
5. virtual stack lowering；
6. effect / handler frame lowering；
7. continuation capture / copy / restore lowering；
8. symbol-space-chain transition lowering；
9. lookup / slot operation lowering；
10. jump fixup；
11. peephole；
12. debug / trace injection；
13. verification。

## 4.6 LIR 与 bytecode 的关系

- LIR 应有自己的 opcode vocabulary；
- bytecode 可以复用某些名字，但不能把 LIR 定义成 `Opcode = BytecodeOpcode`；
- `LIR -> bytecode` 只允许：
  - encode；
  - pack；
  - relocate；
  - attach tables；
- 如果 bytecode compiler 需要重新理解：
  - tail call；
  - effect；
  - host call；
  - scope；则说明 LIR 还没完成。

## 4.7 LIR verifier

至少检查：

- physical register / frame slot 越界；
- call ABI；
- continuation layout；
- effect frame save / restore 配对；
- handler frame push / pop 配对；
- continuation capture / resume 布局；
- ss-chain enter / leave / restore 配对；
- lookup / slot operand 合法；
- no remaining language-level handle / perform / resume；
- relocation target；
- constant pool reference；
- debug metadata；
- instruction operand layout；
- host-call ABI；
- no remaining pseudo instruction。

## 4.8 LIR 完成标准

- LIR 能独立解释低层执行布局；
- bytecode compiler 只编码，不做 semantic lowering；
- effect frame 不再只靠 VM 中的 Python `_EffectFrame`；
- continuation frame、handler frame、ss-chain transition、lookup operation 已全部显式；
- register allocation / host ABI / debug injection 都能说清属于 LIR；
- 若未来 register VM 升级，优先只改 LIR / bytecode / VM，不回改 HIR / MIR。

---

# 5. 三层对照

| 问题 | HIR | MIR | LIR |
| --- | --- | --- | --- |
| 关注点 | 高层语义 | 控制流 / 虚拟寄存器 | Qy 抽象机器 / VM-facing lowering |
| 形状 | 结构化树 | CFG | 线性指令 |
| 知道 binding | 是 | 只保留 ref | 否，只保留已降级引用 |
| 知道 operator signature | 是 | 只保留结果 | 否 |
| 知道 effect declaration | 是 | 显式 effect flow / region | handler frame / continuation frame / ss-chain transition |
| 知道 source syntax | 仅必要 payload | 否 | 否 |
| 知道 Environment | 否（只用实例事实） | 否 | 否 |
| 知道 virtual register | 否 | 是 | 经过分配后不再是 virtual |
| 知道 physical register | 否 | 否 | 是 |
| 知道 bytecode offset | 否 | 否 | relocation / fixup 后可知 |
| 能否被 analyzer 消费 | 是 | 通常否 | 否 |
| 是否能独立 verify | 必须 | 必须 | 必须 |

---

# 6. 当前实现与目标差距

## HIR 当前差距

- `ProgramIR` 名称仍泛；
- `Binding` 仍混合 value；
- `raw_args` 仍为 legacy compatibility；
- literal 仍可能是 Python value；
- 缺少独立 verifier；
- profile / binding / effect refs 还不够正式。

## MIR 当前差距

- 已有 CFG / virtual register；
- 但仍有 `LOAD_HOST` 直接携带 Python object；
- effect region 不够显式；
- join / continuation 语义还偏 opcode 约定；
- verifier 还不覆盖 def-use / liveness / scope pairing。

## LIR 当前差距

- 目前几乎是线性化 MIR；
- 直接复用 bytecode opcode；
- 只有 jump patch、register compaction、极小 peephole；
- 没有独立 opcode vocabulary；
- 没有 virtual stack / handler frame / continuation frame lowering；
- 没有 ss-chain transition / lookup operation 显式建模；
- 没有 host ABI lowering；
- 没有独立 verifier。

---

# 7. 推进原则

- 先稳定 HIR facts，再扩大 MIR；
- 先让 MIR 把控制流说明白，再让 LIR 做低层优化；
- 不要为了“快点执行”把 HIR 问题塞给 MIR；
- 不要为了“快点编码”把 MIR 问题塞给 bytecode compiler；
- 不要让 VM 成为所有未完成 lowering 的垃圾桶。
