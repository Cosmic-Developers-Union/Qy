# 核心语言严格语义

本文档给出 QyLang 核心语言的严格语义, 形式化为 Lean 4 类型定义与归纳谓词. 所谓核心语言, 是指宏展开之后、任何中间表示降级之前的语言形态. 核心语言是用户直接面对的语言的语义本体; 所有后续的 HIR、MIR、LIR、字节码都是对核心语言语义的不同实现策略, 不得反过来修改核心语言的语义.

核心语言的语义包括三个层面: 抽象语法 (描述核心语言所承认的所有语法形态及其结构), 静态语义 (描述程序必须满足的良构条件、作用域规则、类型规则、效果声明规则), 动态语义 (描述良构程序在求值过程中如何一步一步地化简为最终结果, 以及如何处理控制流、并发、效果、模块).

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