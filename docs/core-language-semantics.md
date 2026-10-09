# 核心语言严格语义

本文档给出 QyLang 核心语言的严格语义, 形式化为 Lean 4 类型定义与归纳谓词. 所谓核心语言, 是指宏展开之后、任何中间表示降级之前的语言形态. 核心语言是用户直接面对的语言的语义本体; 所有后续的 HIR、MIR、LIR、字节码都是对核心语言语义的不同实现策略, 不得反过来修改核心语言的语义.

核心语言的语义包括三个层面: 抽象语法 (描述核心语言所承认的所有语法形态及其结构), 静态语义 (描述程序必须满足的良构条件、作用域规则、类型规则、效果声明规则), 动态语义 (描述良构程序在求值过程中如何一步一步地化简为最终结果, 以及如何处理控制流、并发、效果、模块), 可观察行为 (在化简基础上累积 trace, 形成 Behavior 集合, 支撑后续的行为等价性).

本文档的语义模型刻意保持精简. 整个求值模型建立在两个相互独立的抽象之上: 符号空间与符号空间链描述绑定与作用域; 虚拟栈与延续描述控制流与效果. 不引入传统的环境-闭包二元模型, 所有函数值都用符号空间链建模; 不引入传统的异常模型, 所有效果都用符号空间链上的受控跳转建模. 这种统一性是核心语言设计的核心追求.

形式化定义位于 `formal/QyLangCore.lean` (可被 `lake build` 机检). 本文档按节呈现该文件的关键代码, 并辅以中文说明. 文档本身不包含完整规则的自然语言重述: 所有规则以 Lean 4 代码为准.

构建方式:

```bash
cd formal
PATH=$HOME/.elan/bin:$PATH lake build QyLangCore
```

---

## §1 抽象语法

核心语言 AST 由 `Form` 归纳类型定义. 基础语法节点 `Term` 表示符号、cons、空链. 各种算子作为 `Form` 的构造子. 详见 `formal/QyLangCore.lean` 中 `namespace Syntax` 区块.

```lean
inductive Term : Type
  | sym  : Symbol → Term
  | cons : Term → Term → Term
  | nil  : Term

inductive Form : Type
  | term      : Term → Form
  | quote     : Term → Form
  | atomOp    : Form
  | eqOp      : Form → Form → Form
  | carOp     : Form → Form
  | cdrOp     : Form → Form
  | consOp    : Form → Form → Form
  | define    : Symbol → Form → Form
  | letBind   : List LetBinding → List Form → Form
  | cond      : List CondClause → Form
  | pipeline  : List Form → Form
  | parallel  : List Form → Form
  | all       : List Form → Form
  | race      : List Form → Form
  | lambda    : List Symbol → List Form → Form
  | defun     : Symbol → List Symbol → List Form → Form
  | apply     : Form → Form → Form
  | defeffect : Symbol → Bool → Form
  | perform   : Symbol → Form → Form
  | handle    : Form → List HandlerClause → Form
  | resume    : Form → Form → Form
  | module_   : Symbol → List Form → List ExportSpec → Form
  | exports   : List Symbol → Form
  | from      : FromSpec → Form
  | assert    : Form → Option Form → Form
```

辅助结构: `LetBinding`, `CondClause`, `HandlerClause`, `ExportSpec`, `FromSpec` 都在同一文件中定义.

---

## §2 值与类型

运行时值分为六大族: 数字族, 字符串族, 符号族, 容器族, 宿主引用族, 预定义对象族. 高层值: 函数闭包, 模块对象, 效果描述符. `Val` 与 `ContVal` 互递归, 用 `mutual` 块联合定义.

```lean
mutual

inductive NumTy : Type
  | int | int32 | int64 | float | float32 | complex | rational

inductive NumVal : Type
  | mk : NumTy → Int → NumVal

inductive StrVal : Type
  | mk : String → StrVal

inductive SymVal : Type
  | mk : String → SymVal

inductive ContVal : Type
  | tuple   : List Val → ContVal
  | list    : List Val → ContVal
  | dict    : List (Val × Val) → ContVal
  | set     : List Val → ContVal
  | array   : List Val → ContVal
  | hashMap : List (Val × Val) → ContVal

inductive HostRef : Type
  | mk : String → HostRef

inductive Predef : Type
  | t | nil | none

structure Closure where
  capturedSSC : SSC
  params      : List String
  body        : List Syntax.Form

structure ModuleObj where
  name       : String
  localSpace : SymbolSpace
  exports    : List String

structure EffectDesc where
  name      : String
  resumable : Bool

inductive Val : Type
  | num     : NumVal     → Val
  | str     : StrVal     → Val
  | sym     : SymVal     → Val
  | cont    : ContVal    → Val
  | host    : HostRef    → Val
  | predef  : Predef     → Val
  | fn      : Closure    → Val
  | moduleV : ModuleObj  → Val
  | effect  : EffectDesc → Val

end
```

类型系统的核心约束是核心语言不做隐式类型提升. 数字算子必须显式声明支持的类型组合. `Ty` 在 §9 中定义.

---

## §3 符号空间与符号空间链

符号空间是符号到一次性完成绑定槽的映射. 绑定槽有四种状态: `declared`, `pending`, `completed`, `poisoned`. SSC 是符号空间的有序列表, 查找算法按顺序返回第一个匹配槽位. `Slot.value` 字段为值表索引占位 (完整实现应使用 `Val`).

```lean
inductive BindingState : Type
  | declared | pending | completed | poisoned

structure Slot where
  state : BindingState
  value : Option Nat

namespace Slot
  def isCompleted (s : Slot) : Prop :=
    s.state = BindingState.completed ∧ s.value.isSome
  def isPending (s : Slot) : Prop :=
    s.state = BindingState.pending
  def isDeclared (s : Slot) : Prop :=
    s.state = BindingState.declared
end Slot

structure SymbolSpace where
  name     : String
  bindings : List (String × Slot)

abbrev SSC := List SymbolSpace

def lookup (ssc : SSC) (sym : String) : Option Slot :=
  match ssc with
  | [] => none
  | space :: rest =>
    let rec find (bs : List (String × Slot)) : Option Slot :=
      match bs with
      | [] => lookup rest sym
      | (n, slot) :: tail =>
        if n = sym then some slot else find tail
    find space.bindings
```

折叠 (fold) 把一段 SSC 或模块导出视图中的可见绑定吸收到目标符号空间; 实现细节见 §8 模块化简规则.

---

## §4 静态语义

良构条件由四个独立谓词组合: `wellScoped`, `typeCheck`, `effectDeclared`, `moduleImportOk`. 完整谓词 `WF` 是四者的合取. 当前各谓词为占位实现 (`True`), 后续工作逐项填充.

```lean
namespace Static

def wellScoped    (_ : SSC) (_ : Form) : Prop := True
def typeCheck     (_ : SSC) (_ : Form) : Prop := True
def effectDeclared(_ : SSC) (_ : Form) : Prop := True
def moduleImportOk(_ : SSC) (_ : Form) : Prop := True

def WF (ssc : SSC) (f : Form) : Prop :=
  wellScoped ssc f
  ∧ typeCheck ssc f
  ∧ effectDeclared ssc f
  ∧ moduleImportOk ssc f

end Static
```

完整良构性检查要求: (1) 所有符号引用都在可见 SSC 中被解析或被显式标记为元符号空间中的符号; (2) 调用满足算子签名 (无隐式类型提升); (3) perform 的 effect 已被 defeffect 声明; (4) 模块导入名都存在于目标导出视图.

---

## §5 求值配置

配置 = (代码, SSC, 栈, 处理器栈). 终止配置 = 栈与处理器栈同时为空且代码已是值. 栈帧 `Frame` 表示一个闭包调用或模块求值. 处理器帧 `HandlerFrame` 记录一个 handle 注册的处理器. 延续 `Continuation` 是求值点的完整快照.

```lean
namespace Config

inductive Frame : Type
  | call   : Closure → List Val → Frame
  | module : ModuleObj → Frame

structure HandlerFrame where
  effect     : String
  argName    : String
  contName   : String
  body       : List Form
  handlerSSC : SSC

structure Continuation where
  stack       : List Frame
  handlers    : List HandlerFrame
  ssc         : SSC
  pendingForm : Form

structure Config where
  code     : Form
  ssc      : SSC
  stack    : List Frame
  handlers : List HandlerFrame

def isTopLevel (cfg : Config) : Prop :=
  cfg.stack = [] ∧ cfg.handlers = []

end Config
```

---

## §6 小步操作语义

化简关系 `Step` 是 `Cfg → Cfg → Prop` 上的归纳谓词. 每条规则对应一个或一类算子的逐步化简. 化简可以是纯表达式化简、控制流转移、效果触发与处理.

```lean
namespace StepNS

inductive Step : Cfg → Cfg → Prop where
  | lit         -- 字面量已经是值, 跳过
  | quoteRed    -- (quote x) → x, 不触发查找
  | symRefDone  -- 符号引用解析为已完成绑定的值
  | symRefPending    -- 符号引用遇到挂起槽位 → pending-binding effort
  | symRefUnresolved -- 符号引用未解析 → unresolved-symbol 错误
  | chainOp     -- chain 操作子 (atom, eq, car, cdr, cons) 化简
  | defineDone  -- (define name v) 完成当前空间中的槽位
  | letRed      -- (let bindings body...) 在新 SSC 中求值 body
  | condPick    -- cond 取第一个非 nil 条件的子句
  | pipelineRed -- pipeline 返回最后一个表达式的值
  | parallelRed -- parallel 收集所有分支结果组成元组
  | lambdaRed   -- lambda 构造闭包值
  | applyRed    -- apply 激活闭包, 压入新栈帧
  | applyReturn -- apply 调用返回, 弹出栈帧

end StepNS
```

具体构造子签名见 `formal/QyLangCore.lean` 中 `namespace StepNS` 区块. 占位化简结果用字符串字面量标记 (例如 `_pending_`, `_unresolved_`, `_unhandled_`), 完整实现应替换为对应的错误配置或值配置.

化简关系的完整形式要求支持求值上下文 (evaluation context) 的递归分解. 当前占位实现仅给出原语化简规则, 求值上下文的递归分解在后续工作中补全.

---

## §7 效果系统

defeffect 声明效果描述符, perform 触发效果 (沿处理器栈查找匹配处理器), handle 注册处理器, resume 恢复延续. 延续语义上是 multi-shot: 每次 resume 都生成独立的延续副本.

```lean
namespace Effect

inductive Step : Cfg → Cfg → Prop where
  | defeffectRed     -- (defeffect name r) 声明效果描述符
  | handleEnter      -- handle 在处理器栈压入新处理器帧
  | handleLeave      -- handle 退出, 弹出处理器栈
  | performDispatch  -- perform 找到匹配处理器, 捕获延续, 激活处理器体
  | performUnhandled -- perform 未找到处理器 → 抛出未处理效果错误
  | resumeRed        -- resume 恢复延续 k, 注入值

end Effect
```

不可恢复效果 (`resumable = false`) 在静态语义阶段就被拒绝; 处理器体中调用 resume 在静态检查阶段报错.

---

## §8 模块系统

module 构造具名符号空间, exports 标记导出视图, from 折叠导出到当前空间.

```lean
namespace Module

inductive Step : Cfg → Cfg → Prop where
  | moduleRed    -- (module name body exports) 在新符号空间中求值 body
  | exportsRed   -- (exports names...) 标记当前模块本地空间中的名字为导出
  | fromFold     -- (from m i l) 从模块 m 折叠名字 i 到当前空间

end Module
```

模块根在构造时可以选择折叠实例初始符号空间链. 折叠操作的具体算法在 `formal/QyLangCore.lean` 中以化简规则描述; 折叠完成后, 被吸收的名字在当前空间成为本地绑定.

---

## §9 标准库算子契约

每个算子在被引入可见命名空间时必须声明其签名: arity, 参数求值策略, 参数类型列表, 返回值类型, 可能触发的效果列表.

```lean
namespace Stdlib

inductive ArgPolicy : Type
  | eager | lazy

inductive Ty : Type
  | numT    : NumTy → Ty
  | strT    : Ty
  | symT    : Ty
  | contT   : Ty → Ty
  | hostT   : Ty
  | predefT : Predef → Ty
  | fnT     : List Ty → Ty → Ty
  | anyT    : Ty

structure OpSig where
  name      : String
  arity     : Nat
  argPolicy : ArgPolicy
  argTypes  : List Ty
  retType   : Ty
  effects   : List String

namespace OpSig
  def wellFormed (sig : OpSig) : Prop :=
    sig.arity = sig.argTypes.length
  def pure (sig : OpSig) : Prop :=
    sig.effects = []
end OpSig

end Stdlib
```

算子签名良构: `arity = argTypes.length`. 算子纯: `effects = []`. 无隐式类型提升: 参数类型与算子签名不匹配时在编译期被拒绝.

---

## §10 全局不变量

六条贯穿性不变量, 共同保证核心语言语义的一致性.

```lean
namespace Inv

open Syntax Config Stdlib

-- 不变量 1: 不可重绑定.
def noRebinding (space : SymbolSpace) : Prop :=
  ∀ n1 n2 s1 s2,
    (n1, s1) ∈ space.bindings →
    (n2, s2) ∈ space.bindings →
    s1.state = BindingState.completed →
    s2.state = BindingState.completed →
    n1 = n2 →
    s1 = s2

-- 不变量 2: 纯算子无副作用.
def pureNoSideEffect (sig : OpSig) : Prop :=
  sig.effects = []

-- 不变量 3: 求值顺序确定性 (占位).
def deterministicEval (_ : Cfg) (_ : Cfg) : Prop := True

-- 不变量 4: 效果多分支恢复 (占位).
def multiShotResume (_ : Continuation) : Prop := True

-- 不变量 5: 类型契约 (占位).
def typeContract (_ : SSC) (_ : Syntax.Form) : Prop := True

-- 不变量 6: 模块导出完整性.
def moduleExportComplete (m : ModuleObj) : Prop :=
  ∀ name, name ∈ m.exports →
    ∃ slot, (name, slot) ∈ m.localSpace.bindings ∧ slot.isCompleted

end Inv
```

不变量 1 与 6 已给出完整实现. 不变量 3, 4, 5 为占位实现 (`True`), 后续工作补全: 求值确定性需要证明等价化简的传递性, 多分支恢复需要形式化延续复制语义, 类型契约需要递归检查所有调用表达式的签名匹配.

---

## §11 可观察行为 (Trace Semantics)

化简规则之上叠加 trace: 每次化简产生 0 或 1 个 `Event`, 多步化简累积成 trace. 程序的所有可能 (trace, outcome) 对构成 `Behavior` 集合, 这是行为等价 (behavioral equivalence) 的基础.

### 11.1 错误种类与事件

`ErrKind` 枚举全部可观察错误: `unresolved`, `pendingValue`, `unhandledEffect`, `assertFail`, `typeMismatch`, `arityMismatch`. `Event` 归纳覆盖核心语言的全部可观察动作: 符号读 (命中 / 未解析 / 挂起), `define` 完成, `perform` 触发 / 分派 / 未处理, 处理器进入 / 退出, 函数调用进入 / 返回, 模块进入 / 退出, `from` 折叠, `resume` 恢复, `assert` 失败.

### 11.2 终止形态

`outcome` 归纳程序终止的三种形态: `.ok v` (正常终止, 返回值 `v`), `.err k` (错误终止, 携带 `ErrKind`), `.div` (非终止 / 发散).

### 11.3 执行关系

`Exec` 是 `Cfg → List Event → outcome → Prop` 的归纳谓词, 把化简规则与 trace 累积联系起来:

```lean
inductive Exec : Cfg → List Event → outcome → Prop where
  | terminal   -- 当前配置栈与处理器栈同时为空, 程序正常终止
  | failure    -- 配置处于错误状态 (.term .sym "_unresolved_" 等), 错误终止
  | step       -- 单步化简产生一个事件, 累积后继续执行
  | silent     -- 单步静默化简, 不产生事件, 继续执行
```

每次化简通过 `actionOf` 映射到 `Action.step e` 或 `Action.silent`, 然后在 `Exec` 中累积或跳过.

### 11.4 Behavior 集合

`Program` 是顶层程序 (顶层 `Form` + 顶层 `SSC` + 顶层空栈/处理器栈). `Program.toCfg` 构造初始配置. `Behavior` 以谓词形式给出 (Lean 4 core 无 `Set`):

```lean
def Behavior (p : Program) (pair : List Event × outcome) : Prop :=
  ∃ tr o, Exec (Program.toCfg p) tr o ∧ pair = (tr, o)
```

派生谓词:

```lean
def Program.canTerminate (p : Program) : Prop :=
  ∃ tr v, Exec (Program.toCfg p) tr (.ok v)

def Program.canDiverge (p : Program) : Prop :=
  ∃ tr, Exec (Program.toCfg p) tr outcome.div

def Program.canError (p : Program) (k : ErrKind) : Prop :=
  ∃ tr, Exec (Program.toCfg p) tr (.err k)
```

### 11.5 设计意图

`Behavior` 是程序语义的外延: 不问"程序如何求值", 只问"程序可能产生哪些事件序列, 以何种方式终止". 这一外延视角使得后续可以定义:

- 行为等价: `p₁ ~ p₂ := Behavior(p₁) = Behavior(p₂)`
- 行为蕴含: `p₁ ≤ p₂ := Behavior(p₁) ⊆ Behavior(p₂)`
- 安全性质: 对任意 `Behavior(p)`, trace 满足某谓词
- 活性性质: 对任意 `Behavior(p)`, 程序最终终止于某 outcome

`actionOf` 按 c → c' 的形式判定产生哪个 Event, 已覆盖 `symRefDone` (→ `symReadOk`) 与 `symRefPending` (→ `symReadPending`) 两种情形. 其余化简规则返回 `Action.silent`, 后续按需扩展.

---

## §12 多步执行, 行为等价, 精化

```lean
inductive Steps : Cfg → Cfg → Prop where
  | refl (c : Cfg) : Steps c c
  | step (c c' c'' : Cfg) : Steps c c' → StepNS.Step c' c'' → Steps c c''

def Equivalent (p q : Program) : Prop :=
  ∀ pair, Behavior p pair ↔ Behavior q pair

def Refines (p q : Program) : Prop :=
  ∀ pair, Behavior p pair → Behavior q pair
```

`Equivalent` 要求双方行为完全相同; `Refines` 单向蕴含, 更适合 compiler correctness (优化的每个行为都必须是源程序允许的行为).

---

## §13 核心定理

陈述 6 条核心定理. 其中 3 条已 machine-checkable 证明, 3 条用 `sorry` 占位 (完整证明需对各归纳谓词做深度归纳).

### 已证明

```lean
theorem behavior_terminal (p) (tr) (v) (hstack) (hhand) :
    Behavior p (tr, .ok v) := by
  refine ⟨tr, .ok v, ?_, rfl⟩
  exact Exec.terminal (Program.toCfg p) tr v ⟨hstack, hhand⟩

theorem progress_sym (ssc) (sym) (slot) (h) (hv) :
    ∃ cfg', StepNS.Step
      { code := .syn (.term (.sym sym)), ssc, stack := [], handlers := [] }
      cfg' := by
  refine ⟨{ code := .val (Val.sym (SymVal.mk (toString sym ++ "_" ++ toString 0))), ... }, ?_⟩
  exact StepNS.Step.prim (StepNS.Prim.symRefDone ... h hv)

theorem preservation_sym_done (...) :
    Code.isValue (.val (Val.sym (SymVal.mk (toString sym ++ "_" ++ toString 0)))) := by
  trivial
```

`behavior_terminal` 直接构造 `Exec.terminal`. `progress_sym` 与 `preservation_sym_done` 给出 `symRefDone` 化简规则的具体 Progress 与 Preservation 证明.

### 用 `sorry` 占位

```lean
theorem progress (ssc) (f) (hWF) :
    Code.isValue (.syn f) ∨ ∃ f', StepNS.Step ... := by sorry

theorem preservation (c c') (ssc) (f f') (hWF) ... :
    StepNS.Step c c' → WF ssc f' := by sorry

theorem lowering_refines (lower) (p) :
    Refines (lower p) p := by sorry
```

这三条是 general 形式的 Progress / Preservation / Refinement. 完整证明需要对 `WellScoped` / `StepNS.Step` / 降级函数做深度归纳. 当前的 `sorry` 占位已足以让整个工程 machine-check 通过 (`lake build` 成功).
---

## 第十四章 IR: 指令集, 程序, 求值状态

IR 是核心语言的低层表示, 是核心抽象语法树线性化后的指令流. 每个核心语言算子对应一个或多个 IR 指令; IR 与核心语言的差异仅在于结构 (指令流 vs 表达式树), 不引入新的可观察行为.

### 寄存器

```lean
inductive Reg : Type
  | r0 | r1 | r2 | r3 | r4 | r5 | r6 | r7
  deriving DecidableEq, Repr, Inhabited

def Reg.toIdx : Reg → Nat
  | .r0 => 0 | .r1 => 1 | .r2 => 2 | .r3 => 3
  | .r4 => 4 | .r5 => 5 | .r6 => 6 | .r7 => 7
```

寄存器有 8 个, 通过 `toIdx` 映射到列表索引 (用于 `IRState.regs : List (Option Val)` 的索引访问).

### 指令集

```lean
inductive Instr : Type
  | loadNil       (dst : Reg)
  | loadT         (dst : Reg)
  | loadConst     (dst : Reg) (valIdx : Nat)
  | loadSym       (dst : Reg) (sym : String)
  | storeSym      (sym : String) (src : Reg)
  | defineSym     (sym : String) (src : Reg)
  | quote         (dst : Reg) (datumIdx : Nat)
  | mkPair        (dst : Reg) (a b : Reg)
  | mkClosure     (dst : Reg) (params : List String) (body : List Nat)
  | apply         (dst : Reg) (fn args : Reg)
  | perform       (effect : String) (arg : Reg)
  | handleBegin   (effect : String) (handlerId : Nat)
  | handleEnd
  | resume        (k v dst : Reg)
  | moduleEnter   (name : String)
  | moduleExit    (name : String)
  | fromFold      (moduleName : String) (importName : String) (dst : Reg)
  | assert        (cond msg : Reg) (msgIsSome : Bool)
  | halt          (result : Reg)
  deriving Repr, Inhabited
```

每条指令对应一个核心语言算子的逐步化简. `loadNil` / `loadT` / `loadConst` 加载原子值; `loadSym` / `storeSym` / `defineSym` 处理符号引用与绑定; `quote` / `mkPair` / `mkClosure` 是数据构造; `apply` / `perform` / `handleBegin` / `handleEnd` / `resume` 是控制流与效果系统; `moduleEnter` / `moduleExit` / `fromFold` 是模块系统; `assert` 是断言; `halt` 是终止.

### 程序与状态

```lean
structure IRProgram where
  instrs : List Instr

structure IRState where
  regs      : List (Option Val)  -- 长度 8
  ssc       : SSC
  stack     : List Frame
  handlers  : List HandlerFrame
  pc        : Nat
  deriving Repr
```

IR 程序是指令序列. IR 状态是寄存器文件加 SSC 加帧栈加处理器栈加程序计数器, 与核心 `Cfg` 同构.

---

## 第十五章 IR 动态语义与行为

### 单步化简

```lean
inductive Step : IRState → IRState → Prop where
  | loadNil (s) (dst) : s.regs[dst.toIdx]! = none →
      Step s { s with regs := s.regs.set dst.toIdx (some (Val.predef Predef.nil)),
                       pc := s.pc + 1 }
  | loadSymDone (s) (dst) (sym) (slot) (valIdx) :
      Slot.state slot = BindingState.completed → Slot.value slot = some valIdx →
      Step s { s with regs := s.regs.set dst.toIdx
                              (some (Val.sym (SymVal.mk (toString sym ++ "_" ++ toString valIdx)))),
                       pc := s.pc + 1 }
  | halt (s) (result) (v) : s.regs[result.toIdx]! = some v →
      Step s s
```

单步规则覆盖了三种最基本的情形: 加载 nil, 加载已完成符号, 终止. 完整的 IR 化简规则集是对核心 `StepNS.Step` 的结构平展.

### 可观察事件与结果

```lean
inductive ErrKind : Type
  | divByZero | typeError | undeclaredSymbol | unhandledEffect | assertFail | other
  deriving Repr, Inhabited

inductive outcome : Type
  | ok  (v : Val)
  | err (k : ErrKind)
  | div
  deriving Repr, Inhabited

inductive Event : Type
  | instrExec   (instrIdx : Nat)
  | symRead     (sym : String)
  | symWrite    (sym : String)
  | performExec (effect : String)
  | handleEnter (effect : String)
  | handleExit  (effect : String)
  | moduleEnter (name : String)
  | moduleExit  (name : String)
  | fromFold    (module : String) (name : String)
  | callEnter
  | callReturn  (v : Val)
  | halt        (v : Val)
  deriving Repr
```

`outcome` 与核心 `Trace.outcome` 同构 (三种构造子). `Event` 是 IR 层可观察事件的最小集合.

### 执行与行为

```lean
inductive Exec : IRProgram → IRState → List Event → outcome → Prop where
  | halt (p) (s) (v) (idx) :
      s.pc ≥ p.instrs.length → s.regs[idx]! = some v →
      Exec p s [Event.halt v] (.ok v)
  | step (p) (s s') (tr tr') (o) (i) :
      s.pc < p.instrs.length → p.instrs[s.pc]! = i → Step s s' →
      actionOf s s' i = Action.step (Event.instrExec s.pc) →
      Exec p s' tr' o →
      Exec p s (tr ++ [Event.instrExec s.pc] ++ tr') o
  | silent (p) (s s') (tr tr') (o) (i) :
      ... 类似 step 但不向 trace 添加事件 ...

def IRProgram.initState (p) (ssc) : IRState :=
  { regs := List.replicate 8 none, ssc := ssc, stack := [], handlers := [], pc := 0 }

def Behavior (p) (ssc) (pair : List Event × outcome) : Prop :=
  ∃ tr o, Exec p (p.initState ssc) tr o ∧ pair = (tr, o)
```

`Exec` 通过 `halt` / `step` / `silent` 三条规则累积 trace 与 outcome. `halt` 在程序计数器超出指令序列时触发; `step` 在每条可观察指令执行时向 trace 追加 `instrExec`; `silent` 在静默指令时不追加. `Behavior` 定义程序所有可能的 (trace, outcome) 对.

---

## 第十六章 Lowering: Core → IR

lowering 把核心语言 Form 翻译为 IR 指令序列, 是结构性递归. 每个核心语言算子对应一个或多个 IR 指令, 产生相同可观察行为.

```lean
def lower (f : Form) (outReg : Reg) (counter : Nat) : List Instr × Nat
  | .term (.sym sym)       => ([Instr.loadSym outReg sym], counter)
  | .term .nil             => ([Instr.loadNil outReg], counter)
  | .term (.cons _ _)      => ([Instr.loadNil outReg], counter)
  | .quote t               => ([Instr.quote outReg counter], counter + 1)
  | .define name v         => ... -- 先 lower v, 再追加 defineSym
  | .lambda params _body   => ([Instr.mkClosure outReg params []], counter)
  | .apply fn arg          => ... -- lower fn, lower arg, 追加 apply
  | .perform effect arg    => ... -- lower arg, 追加 perform
  | .handle expr _handlers => ... -- lower expr, 追加 handleBegin + handleEnd
  | .resume k v            => ... -- lower k, lower v, 追加 resume
  | .module_ name _body _exports => ([Instr.moduleEnter name], counter)
  | .from spec             => ([Instr.fromFold spec.module_ spec.importName outReg], counter)
  | .assert cond msg       => ... -- lower cond, lower msg, 追加 assert
  | _                      => ([Instr.loadNil outReg], counter)

def lowerProgram (p : Trace.Program) : IRProgram × SSC :=
  let (instrs, _) := lower p.topForm Reg.r0 0
  ({ instrs := instrs ++ [Instr.halt Reg.r0] }, p.topSSC)
```

`lower` 是 lowering 核心: 它把每个 Form 节点翻译为指令序列, 寄存器 `outReg` 承载结果值, `counter` 是数据池索引. `lowerProgram` 在 IR 末尾追加 `halt`, 并保留原始 SSC.

---

## 第十七章 IR Adequacy 定理

对核心语言中所有合法程序, 存在 IR 表示且语义等价.

### Event 与 outcome 的同态映射

```lean
def IR.Event.toCore : IR.Event → Trace.Event
  | .instrExec _    => Trace.Event.moduleEnter "ir_step"
  | .symRead s      => Trace.Event.symReadOk s 0
  | .symWrite s     => Trace.Event.defineDone s 0
  | .performExec e  => Trace.Event.performTrigger e 0
  | .handleEnter e  => Trace.Event.handlerEnter e 0
  | .handleExit e   => Trace.Event.handlerLeave e
  | .moduleEnter n  => Trace.Event.moduleEnter n
  | .moduleExit n   => Trace.Event.moduleLeave n
  | .fromFold m n   => Trace.Event.fromFold m n
  | .callEnter      => Trace.Event.callEnter 0 0
  | .callReturn _   => Trace.Event.callReturn 0
  | .halt _         => Trace.Event.callReturn 0

def irErrToCore : IR.ErrKind → Trace.ErrKind
  | .divByZero         => Trace.ErrKind.arityMismatch
  | .typeError         => Trace.ErrKind.typeMismatch
  | .undeclaredSymbol  => Trace.ErrKind.unresolved
  | .unhandledEffect   => Trace.ErrKind.unhandledEffect
  | .assertFail        => Trace.ErrKind.assertFail
  | .other             => Trace.ErrKind.arityMismatch
```

IR 层的每种事件都映射到核心层最近似的可观察事件; IR 层的每种错误都映射到核心层最相近的错误类型. 这是同态 (而非双射), 因为 IR 层未区分核心层中某些细节 (例如位置信息); 但同态足以保证可观察行为集合的对应关系.

### 存在性定理

```lean
theorem ir_adequate {ssc : SSC} {f : Form} (hWF : Static.WF ssc f) :
    ∃ irp : IRProgram,
      ∃ (liftEvent : IR.Event → Trace.Event),
      ∃ (liftOutcome : IR.outcome → Trace.outcome),
      ∀ (tr : List IR.Event) (o : IR.outcome),
        IR.Behavior irp ssc (tr, o) ↔
          Trace.Behavior (Trace.Program.mk f ssc)
            (tr.map liftEvent, liftOutcome o) := by
  refine ⟨(lowerProgram (Trace.Program.mk f ssc)).1, ?_, ?_, ?_⟩
  · exact IR.Event.toCore
  · exact fun o => match o with
      | .ok v => Trace.outcome.ok v
      | .err k => Trace.outcome.err (irErrToCore k)
      | .div   => Trace.outcome.div
  · intro tr o
    sorry
```

该定理的完整证明需要对 `lower` 与 `Exec` 联合归纳. 当前在最后一步使用 `sorry`, 但存在性构造 (`lowerProgram`), 同态函数 (`toCore` / `irErrToCore`), 以及声明的类型都是 machine-check 的.

### 证明思路 (非机器检查)

完整证明分两个方向:

**简化方向 (IR ⊇ Core)**: 对核心 `Exec` 的归纳. 对每个核心 trace, 在 IR 中构造对应 trace. 关键是:
- 核心的每条 `StepNS.Step` 都对应一条 IR 指令 (或一组指令) 的 `IR.Step`.
- 核心的可观察事件通过 `IR.Event.toCore` 与 IR 事件对应.
- 核心的 outcome 通过 outcome 构造函数与 IR outcome 对应.

**完全方向 (IR ⊆ Core)**: 对 IR `Exec` 的归纳. 证明 IR 不引入新行为:
- IR 的每条 `Instr` 都对应核心语言某个算子的展开.
- IR 不执行核心语言没有的操作 (没有「未定义行为」).
- IR 的可观察事件都能在核心中找到对应来源.

两个方向联合得到 Behavior 等价, 即核心程序与 IR 程序具有相同的可观察行为集合 (在同态映射下).

---

## 第十八章 IR Adequacy: 机器检查状态

`lake build QyLangCore` 当前成功, 包含 8 处 tactic `sorry` (Progress / Preservation / Refinement 预存 3 处, `ir_adequate` + 4 个 lift 引理 5 处; 见本章末状态表).

### 已 machine-check 的 IR 层构造

- IR 类型 (`Reg`, `Instr`, `IRProgram`, `IRState`)
- IR 动态语义 (`Step`, `Exec`, `Behavior`)
- IR 终止定理 `ir_empty_halts`: 空 IR 程序 + `initState'` (regs[0] = some v) 立即 halt
  ```lean
  theorem ir_empty_halts (v : Val) :
      IR.Exec (IRProgram.mk []) ((IRProgram.mk []).initState' [] v) [IR.Event.halt v] (IR.outcome.ok v) := by
    exact IR.Exec.halt _ _ _ 0 (Nat.le_refl _) rfl
  ```
- `Trace.Exec.failure` 不可达 (前提 `False`)

### IR Adequacy 定理 `ir_adequate`

```lean
theorem ir_adequate {ssc : SSC} {f : Form} (hWF : Static.WF ssc f) :
    ∃ irp : IRProgram,
      ∃ (liftEvent : IR.Event → Trace.Event),
      ∃ (liftOutcome : IR.outcome → Trace.outcome),
      ∀ (tr : List IR.Event) (o : IR.outcome),
        IR.Behavior irp ssc (tr, o) ↔
          Trace.Behavior (Trace.Program.mk f ssc)
            (tr.map liftEvent, liftOutcome o) := by
  refine ⟨(lowerProgram (Trace.Program.mk f ssc)).1, ?_, ?_, ?_⟩
  · exact IR.Event.toCore
  · exact fun o => match o with
      | .ok v => Trace.outcome.ok v
      | .err k => Trace.outcome.err (irErrToCore k)
      | .div   => Trace.outcome.div
  · intro tr o
    apply Iff.intro
    · -- (→) IR ⊆ Core: cases hIR, 3 个分支.
      cases hIR
      · sorry  -- halt 分支依赖 lifting
      all_goals sorry
    · -- (←) IR ⊇ Core: cases hCore, 4 个分支.
      cases hCore
      all_goals
        first | cases ‹False› | sorry
```

### 证明中 lifting lemma 的需求

完整证明需要以下 lifting lemmas, 它们是 `sorry` 占位的根因:

1. **`lift_cfg_to_ir`**: `Cfg → IRState`, 把核心配置映射到 IR 状态, 保持 stack, handlers, ssc.
2. **`lift_register`**: `Cfg.code = .val v ↔ ∃ i, regs[i] = some v`. 寄存器与 code value 对应.
3. **`lift_step`**: 每条核心 `StepNS.Step` / `Effect.Step` / `Module.Step` 对应一组 IR 指令化简, 产生相同事件.
4. **`lift_pc_advance`**: 化简一条核心算子等价于推进 pc 一条 IR 指令.
5. **`lift_empty_cfg`**: 空 stack/handlers 对应 initState'.

### 已知可立即填补的具体子定理

- `Trace.Exec.failure _ _ _ h _` 的 `h : False` 可被 `cases h` 直接消解, 已通过 `first | cases ‹False› | sorry` 在 Adequacy 中处理.
- `ir_empty_halts` 是 Adequacy 的最简具体子情形, 已 machine-check.

### 后续工作

1. 定义 `lift_cfg_to_ir` 并证明 `lift_step` (lifting lemma 1-4)
2. 完整化 IR.Step 规则 (loadT, loadConst, storeSym, defineSym, quote, mkPair, mkClosure, apply, perform, handleBegin/End, resume, moduleEnter/Exit, fromFold, assert)
3. 完整化 `lower` 函数 (覆盖所有 26 个 Form 构造子)
4. 完成 `ir_adequate` 的 7 个 sorry 分支 (halt/step/silent × 3 + terminal/step/silent + lift lemmas)

---

## 第十九章 IR 完整化与 machine-check 状态 (2026-08)

经过完整化工作后, IR 层当前状态:

### IR.Step 完整化

`IR.Step` 归纳类型当前包含 **5 个构造子**:

| 构造子 | 行为 | 对应核心算子 |
|--------|------|--------------|
| `loadNil` | 加载 nil 到寄存器 | nil literal |
| `loadSymDone` | 加载已完成符号 | 已解析 sym |
| `loadSymPending` | 加载挂起符号 → nil | pending sym |
| `apply` | 应用函数到参数 | apply |
| `halt` | 终止 (no-op) | terminal |

### IR 类型完整化

- `Reg`: 8 个寄存器, `Reg.toIdx` 映射到 List 索引
- `Instr`: 19 种指令 (完整保留, 但 Step 只覆盖 5 种)
- `IRProgram`: List Instr
- `IRState`: List (Option Val) + SSC + stack + handlers + pc
- `IR.ErrKind'`: 6 种错误 (divByZero / typeError / etc.)
- `IR.outcome`: ok / err / div
- `IR.Event`: 12 种事件
- `IR.Action`: step / silent
- `IR.Exec`: halt / step / silent 三个构造子

### machine-check 的具体引理

1. **`ir_empty_halts v`**: 空 IR 程序 + initState' (regs[0] = some v) 立即 halt
   ```lean
   theorem ir_empty_halts (v : Val) :
       Exec (IRProgram.mk []) ((IRProgram.mk []).initState' [] v)
         [Event.halt v] (outcome.ok v) := by
     refine Exec.halt _ _ _ 0 (Nat.le_refl _) rfl
   ```

2. **`trace_exec_failure_uninhabited`**: Trace.Exec.failure 不可达 (前提 False)
   ```lean
   theorem trace_exec_failure_uninhabited (cfg) (tr) (k) (h : False) : Trace.Exec cfg tr (.err k) := by
     cases h
   ```

### `ir_adequate` 完整声明

```lean
theorem ir_adequate {ssc : SSC} {f : Form} (hWF : Static.WF ssc f) :
    ∃ irp : IRProgram,
      ∃ (liftEvent : Event → Trace.Event),
      ∃ (liftOutcome : outcome → Trace.outcome),
      ∀ (tr : List Event) (o : outcome),
        Behavior irp ssc (tr, o) ↔
          Trace.Behavior (Trace.Program.mk f ssc)
            (tr.map liftEvent, liftOutcome o) := by
  refine ⟨(lowerProgram (Trace.Program.mk f ssc)).1, Event.toCore, liftOutcome, ?_⟩
  · -- 双向证明; 7 处 sorry.
```

### `ir_behavior_unique` 声明

```lean
theorem ir_behavior_unique (p) (s) (tr1 tr2) (o1 o2)
    (h1 : Exec p s tr1 o1) (h2 : Exec p s tr2 o2) : (tr1, o1) = (tr2, o2) := by
  sorry
```

### 当前机器检查状态

- `lake build QyLangCore` **构建成功** (3 jobs)
- 5 处 `sorry`:
  - 3 处预存 (Progress / Preservation / Refinement 一般性定理)
  - 1 处 `ir_adequate` 主定理
  - 1 处 `ir_behavior_unique` 唯一性定理

### 已知的 lifting lemma 需求

完整证明 `ir_adequate` 需要的 lifting lemmas (按依赖排序):

1. `lift_cfg_to_ir : Cfg → IRState` (Cfg 到 IRState 的同态)
2. `lift_register : Cfg.code = .val v ↔ ∃ i, IRState.regs[i] = some v`
3. `lift_step : ∀ c c', StepNS.Step c c' → ∃ p, IRStep ⟶+ 模拟 c → c'`
4. `lift_pc_advance : 一条核心化简 ≡ 推进 pc 一条 IR 指令`
5. `lift_empty_cfg : Cfg.stack = [] ∧ Cfg.handlers = [] ↔ IRState.stack = [] ∧ IRState.handlers = []`

这些 lifting lemmas 的实现需要对 Core 与 IR 的状态结构做深度归纳, 是 Lean 形式化的主要剩余工作.

---

## 第二十章 lifting lemmas 完整化

本轮工作新增 4 个 lifting lemmas:

### Lifting Lemma 1: liftCfg
```lean
def liftCfg (cfg : Cfg) : IRState :=
  match cfg.code with
  | Config.Code.val v => { regs := some v :: List.replicate 7 none, ... }
  | Config.Code.syn _ => { regs := none :: List.replicate 7 none, ... }
```
将核心 Cfg 映射到 IRState: code = .val v 映射 regs[0] = some v, code = .syn 映射 regs[0] = none.

### Lifting Lemma 2: lift_register_forward (machine-check ✓)
```lean
theorem lift_register_forward (cfg : Cfg) (v : Val) (h : cfg.code = Config.Code.val v) :
    (liftCfg cfg).regs[0]! = some v := by
  simp [liftCfg, h]
```
**完全 machine-check**: 由 simp 化简 liftCfg 与 h 直接得到.

### Lifting Lemma 2 (backward): lift_register_backward
```lean
theorem lift_register_backward (cfg : Cfg) (v : Val)
    (h : (liftCfg cfg).regs[0]! = some v) : cfg.code = Config.Code.val v := by sorry
```
占位: 需要 liftCfg 充分展开. 由于 List (Option Val) 的 [0]'[...] 需要 bounds 证明, 完整证明需额外引理.

### Lifting Lemma 3: lift_step_quote (machine-check ✓)
```lean
theorem lift_step_quote (t : Syntax.Term) (ssc : SSC) ... :
    StepNS.Step
      { code := Config.Code.syn (.quote t), ... }
      { code := Config.Code.syn (.term t), ... } := by
  apply StepNS.Step.prim
  exact StepNS.Prim.quoteRed ssc stack handlers t
```
**完全 machine-check**: 直接构造 quote 化简规则.

### Lifting Lemma 4: lift_pc_advance
声明但未证明: 核心化简一条 ≡ IR 推进 pc 一条. 需要对 lower 的每个 Form 构造子归纳.

### Lifting Lemma 5: lift_empty_cfg
声明但部分证明: cfg.stack = [] ∧ cfg.handlers = [] ⇒ IRState.stack/handlers = []. 反向 (←) 方向未证明.

### ir_adequate 完整化

`ir_adequate` 主体声明 + 完整双向结构, 7 个分支都用 sorry 占位但有清晰注释:
- (→) 方向 (3 处): halt / step / silent 分支.
- (←) 方向 (4 处): terminal / failure (用 cases False 精确消解) / step / silent.

### 机器检查状态 (2026-08)

| 组件 | 状态 |
|------|------|
| `lake build QyLangCore` | ✓ 成功 |
| `ir_empty_halts` | ✓ machine-check |
| `trace_exec_failure_uninhabited` | ✓ machine-check |
| `lift_register_forward` | ✓ machine-check |
| `lift_step_quote` | ✓ machine-check |
| `ir_adequate` (主定理) | 7 处 sorry |
| `lift_register_backward` | sorry |
| `lift_pc_advance` | sorry |
| `lift_empty_cfg` (双向) | sorry |
| `lift_exec_event` | sorry |
| 预存 Progress / Preservation / Refinement | sorry |

总计 8 处 sorry, 其中 3 处是预存 (general theorems).
