Qy Operator System

Pure Operator

定义

Pure Operator 表示纯求值算子。

Pure Operator 具有：

- eager evaluation
- immutable semantics
- deterministic result
- no runtime effect
- no env mutation
- cacheable
- parallelizable
- statically analyzable

Pure Operator 构成：

```text
Value -> Value
```

Qy 核心 Pure Operator：

- identity返回输入值

- equal判断值相等性

- not逻辑取反

- -

数值加法

- -

数值减法

- -

数值乘法

- / 数值除法

- list构造列表

- object构造对象

- get读取对象/列表成员

- assoc创建新对象字段

- concat拼接字符串或列表

---

Scope Operator

定义

Scope Operator 表示作用域构造算子。

Scope Operator 控制：

- lexical binding
- closure capture
- callable creation
- namespace visibility
- symbol resolution chain

Scope Operator 构成：

```text id="jlwmzu"
Env -> Scoped Evaluation Context
```

Qy 核心 Scope Operator：

- let创建局部绑定

- lambda创建匿名算子

- defun创建命名算子绑定

- component创建组件定义

- module创建模块作用域

---

Control Operator

定义

Control Operator 表示求值控制算子。

Control Operator 控制：

- evaluation order
- branch selection
- short-circuit
- repetition
- evaluation timing

Control Operator 构成：

```text id="jlwmzu"
Form -> Controlled Evaluation
```

Qy 核心 Control Operator：

- if条件分支求值

- cond多分支条件求值

- and短路逻辑与

- or短路逻辑或

- loop重复求值控制

- return提前结束当前求值

---

Effect Operator

定义

Effect Operator 表示 runtime effect 算子。

Effect Operator 具有：

- runtime dependency
- external interaction
- scheduler effect
- possible nondeterminism
- possible side effect

Effect Operator 控制：

- runtime execution
- async scheduling
- state interaction
- IO semantics
- execution graph behavior

Effect Operator 构成：

```text id="jlwmzu"
Computation -> Runtime Effect
```

Qy 核心 Effect Operator：

- load加载外部资源

- save写入外部资源

- call调用宿主能力

- parallel声明并行执行

- cache声明结果缓存

- spawn创建异步任务

- await等待异步结果

- state访问运行时状态

---

Meta Operator

定义

Meta Operator 表示语言元算子。

Meta Operator 控制：

- symbolic tree
- evaluator semantics
- macro expansion
- AST transformation
- language rewriting

Meta Operator 构成：

```text id="jlwmzu"
AST -> AST
```

Qy 核心 Meta Operator：

- quote 返回未求值 symbolic form

- quasiquote 构造 symbolic template

- unquote局部恢复求值

- unquote-splicing 展开 symbolic list

- macro 定义 AST 变换规则

- eval 执行 symbolic form
