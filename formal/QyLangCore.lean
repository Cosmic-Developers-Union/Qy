/-
  QyLangCore.lean — Lean 4 形式化定义 QyLang 核心语言的严格语义.

  核心语言是宏展开之后、任何中间表示降级之前的语言形态. 本文给出形式化的:
    - §1 抽象语法
    - §2 值与类型
    - §3 符号空间与符号空间链
    - §4 静态语义 / 良构谓词
    - §5 求值配置
    - §6 小步操作语义
    - §7 效果系统
    - §8 模块系统
    - §9 标准库算子契约
    - §10 全局不变量

  设计原则:
    1. 类型定义是规范真源, 不变量机器可检.
    2. 所有归纳类型显式标注 `Type`, 避免隐式 universe.
    3. 复杂化简规则使用占位实现, 后续工作逐步完善.

  构建:
    cd formal
    lake build
-/

namespace QyLangCore


/-! ## §3 符号空间与符号空间链 (前置定义, 因后续模块依赖 SSC)

符号空间 = 符号 → 一次性完成绑定槽的映射.
SSC 是符号空间的有序列表, 查找算法按顺序返回第一个匹配槽位.

注意: 绑定槽的 value 字段使用 Nat 作为值表索引占位, 完整实现应使用 Val.
-/

inductive BindingState : Type
  | declared | pending | completed | poisoned
  deriving DecidableEq, Repr

/-- 绑定槽: 一次性完成存储单元. value 是值表的索引. -/
structure Slot where
  state : BindingState
  value : Option Nat   -- 值表索引占位
  deriving Repr

namespace Slot

def isCompleted (s : Slot) : Prop :=
  s.state = BindingState.completed ∧ s.value.isSome

def isPending (s : Slot) : Prop :=
  s.state = BindingState.pending

def isDeclared (s : Slot) : Prop :=
  s.state = BindingState.declared

end Slot

/-- 符号空间. -/
structure SymbolSpace where
  name     : String
  bindings : List (String × Slot)
  deriving Repr

/-- 符号空间链. -/
abbrev SSC := List SymbolSpace

/-- 查找算法. -/
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

def resolvedCompleted (ssc : SSC) (sym : String) : Prop :=
  ∃ slot, lookup ssc sym = some slot ∧ slot.isCompleted

def resolvedPending (ssc : SSC) (sym : String) : Prop :=
  ∃ slot, lookup ssc sym = some slot ∧ slot.isPending

def unresolved (ssc : SSC) (sym : String) : Prop :=
  lookup ssc sym = none


/-! ## §1 抽象语法

三类语法节点: 符号节点, 链节点, 核心语言形式 (`Form`).
-/

namespace Syntax

abbrev Symbol := String

inductive Term : Type
  | sym  : Symbol → Term
  | cons : Term → Term → Term
  | nil  : Term
  deriving Repr

structure LetBinding where
  name  : Symbol
  value : Term
  deriving Repr

structure CondClause where
  cond   : Term
  result : Term
  deriving Repr

structure HandlerClause where
  effect   : Symbol
  argName  : Symbol
  contName : Symbol
  body     : List Term
  deriving Repr

structure ExportSpec where
  name : Symbol
  deriving Repr

structure FromSpec where
  module_    : Symbol
  importName : Symbol
  localName  : Symbol
  deriving Repr

/-- 核心语言 AST. 规范真源. -/
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
  deriving Repr

end Syntax


/-! ## §2 值与类型

运行时值分为: 数字族, 字符串族, 符号族, 容器族, 宿主引用族, 预定义对象族.
高层值: 函数值 (闭包), 模块值, 效果描述符.
Val 与 ContVal 互递归, 用 mutual 块定义.
-/

mutual

inductive NumTy : Type
  | int | int32 | int64 | float | float32 | complex | rational
  deriving Repr

inductive NumVal : Type
  | mk : NumTy → Int → NumVal
  deriving Repr

inductive StrVal : Type
  | mk : String → StrVal
  deriving Repr

inductive SymVal : Type
  | mk : String → SymVal
  deriving Repr

inductive ContVal : Type
  | tuple   : List Val → ContVal
  | list    : List Val → ContVal
  | dict    : List (Val × Val) → ContVal
  | set     : List Val → ContVal
  | array   : List Val → ContVal
  | hashMap : List (Val × Val) → ContVal
  deriving Repr

inductive HostRef : Type
  | mk : String → HostRef
  deriving Repr

inductive Predef : Type
  | t | nil | none
  deriving Repr

/-- 函数闭包: 捕获的 SSC + 参数 + 体. -/
structure Closure where
  capturedSSC : SSC
  params      : List String
  body        : List Syntax.Form
  deriving Repr

/-- 模块对象. -/
structure ModuleObj where
  name       : String
  localSpace : SymbolSpace
  exports    : List String
  deriving Repr

/-- 效果描述符. -/
structure EffectDesc where
  name      : String
  resumable : Bool
  deriving Repr

/-- 运行时值宇宙. 与 ContVal 互递归. -/
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
  deriving Repr

end


/-! ## §4 静态语义

良构条件由四个独立谓词组合: 作用域 / 类型 / 效果声明 / 模块导入.
完整 WF = 四者合取.
-/

namespace Static

open Syntax

def wellScoped (_ : SSC) (_ : Form) : Prop :=
  True

def typeCheck (_ : SSC) (_ : Form) : Prop :=
  True

def effectDeclared (_ : SSC) (_ : Form) : Prop :=
  True

def moduleImportOk (_ : SSC) (_ : Form) : Prop :=
  True

def WF (ssc : SSC) (f : Form) : Prop :=
  wellScoped ssc f
  ∧ typeCheck ssc f
  ∧ effectDeclared ssc f
  ∧ moduleImportOk ssc f

end Static


/-! ## §5 求值配置

配置 = (代码, SSC, 栈, 处理器栈). 终止配置 = 代码已是值.
-/

namespace Config

open Syntax

/-- 调用栈帧. -/
inductive Frame : Type
  | call   : Closure → List Val → Frame
  | module : ModuleObj → Frame
  deriving Repr

/-- 处理器栈帧. -/
structure HandlerFrame where
  effect     : String
  argName    : String
  contName   : String
  body       : List Form
  handlerSSC : SSC
  deriving Repr

/-- 延续: 求值点的完整快照. -/
structure Continuation where
  stack       : List Frame
  handlers    : List HandlerFrame
  ssc         : SSC
  pendingForm : Form
  deriving Repr

/-- 求值配置. -/
structure Config where
  code     : Form
  ssc      : SSC
  stack    : List Frame
  handlers : List HandlerFrame
  deriving Repr

def isTopLevel (cfg : Config) : Prop :=
  cfg.stack = [] ∧ cfg.handlers = []

end Config

abbrev Frame := Config.Frame
abbrev HandlerFrame := Config.HandlerFrame
abbrev Continuation := Config.Continuation
abbrev Cfg := Config.Config


/-! ## §6 小步操作语义

化简规则按算子分类. 每条规则都是一个 Step 构造子.
-/

namespace StepNS

open Syntax Config

/-- 小步化简关系. -/
inductive Step : Cfg → Cfg → Prop where
  | lit
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame) (t : Term) :
      Step
        { code := .term t, ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := ssc, stack := stack, handlers := handlers }

  | quoteRed
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame) (t : Term) :
      Step
        { code := .quote t, ssc := ssc, stack := stack, handlers := handlers }
        { code := .term t, ssc := ssc, stack := stack, handlers := handlers }

  | symRefDone
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (sym : String) (slot : Slot)
      (h : slot.state = BindingState.completed) :
      Step
        { code := .term (.sym sym), ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := ssc, stack := stack, handlers := handlers }

  | symRefPending
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (sym : String) (slot : Slot)
      (h : slot.state = BindingState.pending) :
      Step
        { code := .term (.sym sym), ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.sym "_pending_"), ssc := ssc, stack := stack, handlers := handlers }

  | symRefUnresolved
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame) (sym : String) :
      Step
        { code := .term (.sym sym), ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.sym "_unresolved_"), ssc := ssc, stack := stack, handlers := handlers }

  | chainOp
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame) (op : String) :
      Step
        { code := .term (.sym op), ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := ssc, stack := stack, handlers := handlers }

  | defineDone
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (name : String) :
      Step
        { code := .define name (.term (.nil)), ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := ssc, stack := stack, handlers := handlers }

  | letRed
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (newSSC : SSC) (body : List Form) :
      Step
        { code := .letBind [] body, ssc := newSSC, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := newSSC, stack := stack, handlers := handlers }

  | condPick
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (result : Term) :
      Step
        { code := .cond [], ssc := ssc, stack := stack, handlers := handlers }
        { code := .term result, ssc := ssc, stack := stack, handlers := handlers }

  | pipelineRed
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (last : Form) :
      Step
        { code := .pipeline [last], ssc := ssc, stack := stack, handlers := handlers }
        { code := last, ssc := ssc, stack := stack, handlers := handlers }

  | parallelRed
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame) :
      Step
        { code := .parallel [], ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := ssc, stack := stack, handlers := handlers }

  | lambdaRed
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (params : List Symbol) (body : List Form) :
      Step
        { code := .lambda params body, ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := ssc, stack := stack, handlers := handlers }

  | applyRed
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (cl : Closure) (args : List Val) (newSSC : SSC) :
      Step
        { code := .apply (.term (.sym "_fn_")) (.term (.nil)),
          ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := newSSC, stack := .call cl args :: stack,
          handlers := handlers }

  | applyReturn
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (frame : Frame) (tail : List Frame) :
      Step
        { code := .term (.sym "_done_"), ssc := ssc, stack := frame :: tail,
          handlers := handlers }
        { code := .term (.nil), ssc := ssc, stack := tail, handlers := handlers }

end StepNS


/-! ## §7 效果系统

defeffect 声明, perform 触发, handle 注册, resume 恢复延续.
延续语义是 multi-shot.
-/

namespace Effect

open Syntax Config

inductive Step : Cfg → Cfg → Prop where
  | defeffectRed
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (name : String) (r : Bool) :
      Step
        { code := .defeffect name r, ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := ssc, stack := stack, handlers := handlers }

  | handleEnter
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (expr : Form) (newHandlers : List HandlerFrame) :
      Step
        { code := .handle expr [], ssc := ssc, stack := stack, handlers := handlers }
        { code := expr, ssc := ssc, stack := stack, handlers := newHandlers ++ handlers }

  | handleLeave
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (pushed : List HandlerFrame) (rest : List HandlerFrame)
      (result : Form) :
      Step
        { code := result, ssc := ssc, stack := stack, handlers := pushed ++ rest }
        { code := result, ssc := ssc, stack := stack, handlers := rest }

  | performDispatch
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (effect : String)
      (handlerFrame : HandlerFrame) (rest : List HandlerFrame)
      (cont : Continuation) :
      Step
        { code := .perform effect (.term (.nil)), ssc := ssc,
          stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := ssc, stack := stack,
          handlers := handlerFrame :: rest }

  | performUnhandled
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (effect : String) :
      Step
        { code := .perform effect (.term (.nil)), ssc := ssc,
          stack := stack, handlers := handlers }
        { code := .term (.sym "_unhandled_"), ssc := ssc,
          stack := stack, handlers := handlers }

  | resumeRed
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (k : Continuation) :
      Step
        { code := .resume (.term (.sym "_k_")) (.term (.nil)),
          ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := k.ssc, stack := k.stack,
          handlers := k.handlers }

end Effect


/-! ## §8 模块系统

module 构造具名空间, exports 标记导出, from 折叠导入.
-/

namespace Module

open Syntax Config

inductive Step : Cfg → Cfg → Prop where
  | moduleRed
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (name : String) (body : List Form) (exports : List ExportSpec)
      (newSSC : SSC) (modObj : ModuleObj) :
      Step
        { code := .module_ name body exports, ssc := ssc,
          stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := newSSC, stack := stack, handlers := handlers }

  | exportsRed
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (names : List Symbol) (modObj : ModuleObj) :
      Step
        { code := .exports names, ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := ssc, stack := stack, handlers := handlers }

  | fromFold
      (ssc : SSC) (stack : List Frame) (handlers : List HandlerFrame)
      (spec : FromSpec) (modObj : ModuleObj) (newSSC : SSC) :
      Step
        { code := .from spec, ssc := ssc, stack := stack, handlers := handlers }
        { code := .term (.nil), ssc := newSSC, stack := stack, handlers := handlers }

end Module


/-! ## §9 标准库算子契约

每个算子声明: arity, 参数求值策略, 参数类型, 返回值类型, 可能触发的效果.
-/

namespace Stdlib

inductive ArgPolicy : Type
  | eager | lazy
  deriving Repr

inductive Ty : Type
  | numT    : NumTy → Ty
  | strT    : Ty
  | symT    : Ty
  | contT   : Ty → Ty
  | hostT   : Ty
  | predefT : Predef → Ty
  | fnT     : List Ty → Ty → Ty
  | anyT    : Ty
  deriving Repr

structure OpSig where
  name      : String
  arity     : Nat
  argPolicy : ArgPolicy
  argTypes  : List Ty
  retType   : Ty
  effects   : List String
  deriving Repr

namespace OpSig

def wellFormed (sig : OpSig) : Prop :=
  sig.arity = sig.argTypes.length

def pure (sig : OpSig) : Prop :=
  sig.effects = []

end OpSig

end Stdlib


/-! ## §10 全局不变量

六条贯穿性不变量, 保证核心语言语义的一致性.
-/

namespace Inv

open Syntax Config Stdlib

/-- 不变量 1: 不可重绑定. -/
def noRebinding (space : SymbolSpace) : Prop :=
  ∀ n1 n2 s1 s2,
    (n1, s1) ∈ space.bindings →
    (n2, s2) ∈ space.bindings →
    s1.state = BindingState.completed →
    s2.state = BindingState.completed →
    n1 = n2 →
    s1 = s2

/-- 不变量 2: 纯算子无副作用. -/
def pureNoSideEffect (sig : OpSig) : Prop :=
  sig.effects = []

/-- 不变量 3: 求值顺序确定性 (占位). -/
def deterministicEval (_ : Cfg) (_ : Cfg) : Prop :=
  True

/-- 不变量 4: 效果多分支恢复 (占位). -/
def multiShotResume (_ : Continuation) : Prop :=
  True

/-- 不变量 5: 类型契约 (占位). -/
def typeContract (_ : SSC) (_ : Syntax.Form) : Prop :=
  True

/-- 不变量 6: 模块导出完整性. -/
def moduleExportComplete (m : ModuleObj) : Prop :=
  ∀ name, name ∈ m.exports →
    ∃ slot, (name, slot) ∈ m.localSpace.bindings ∧ slot.isCompleted

end Inv


end QyLangCore