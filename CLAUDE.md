# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

QyLang 是 Lisp-like, 基于代数效应的通用编程语言，目标是成为一个可被嵌入的, 高度统一的, 强大的编程语言.

QyLang 设计理念先进, 追求高度的语言内核统一性和实现简洁性, 它以 s-expression 作为唯一语法, 以代数效应作为核心控制抽象, 以
symbol-space 作为env建模, 以 symbol-space-chain 作为作用域建模, 为用户提供一个极简而强大的编程模型.

语法设计上, 以`chain`作为核心构造, `symbol`作为唯一原子, 构建了核心语法, 对于被求值的`chain`, 其首元素被视作`算子`,
它是语言核心操作, 基本上`symbol-space`(`ss`), `symbol-space-chain`(`ssc`), 构建了核心操作体系.

pre-ss 为用户提供了默认且常见的数据类型和操作符的ss, 为用户提供了便利.

基本包含如下几类:

- lisp-ss: 仅定义了 `t`, `nil` 两个 symbol.
- 值ss: number-ss, string-ss, char-ss. 这是在其他编程语言语言中常见的子面量和原子值, 但 QyLang 中没有对应的 literal 语法,
  而是通过预定义的 symbol 来构建这些值, 以保持语言核心的极简性和统一性. (因此你可以在符号空间中定义任何符号的值,
  这是一个非常危险的特性)
- core op: 核心算子, 也是内置算子, 他们通过 ss 的形式提供.
- ext op: 扩展算子, 这是 vm 自己实现的特定算子, 者为嵌入式提供了一些特定的能力, 例如你可以把一个python函数包装成一个 ext
  op, 以在 qy 中调用它(注意, 这一般只能在python实现的vm中完成). 他们通过 ss 的形式提供.
- meta-symbol-space, 唯一的的符号空间, 也是所与 ssc 的起点.

所有的符号空间均位于ssc中, 所有的ssc的首ss都是 meta-symbol-space.

带有名字的 ss 被称为`具名符号空间`, 它构成了QyLang的模块化.

**符号空间中的所有符号绑定不可重新绑定**.

对于 ss/ssc 有两个核心操作: `折叠` 和 `展开`.

`折叠` 是将多个ss所构成了ssc合成为一个 ss 的过程. 对于带有冲突的命名, 会引发 effort.
`展开` 是在一个ss内部展开一个ss/ssc的过程. 它实现了类似python中的`import`功能, 但更为强大和灵活.

在 QyLang(以下简称`qy`)中, 只有一个会操作当前ss的符号绑定: `define`, re-define 会引发 effort.
有三个算子会创建新的符号空间新的ss并绑定当前ss以及其ssc作为自身ssc:

- module: 创建一个符号空间. 多数情况下, qy 会把其他文件作为 module. 因此不常用.
- let: 创建一个匿名符号空间, 并返回其中的计算结果. 这是和 module 的不同点.
- lambda: 创建一个匿名符号空间, 并返回一个算子, 它和let不同的点在于求值方式, lambda 得到的是一个算子.

对于 perform, handle, resume, 他们实际是ssc/ss结构化的自然产物.

如:

```qy
(handle
  (on divide-by-zero () k (resume k 1))
  (+ (/ 1 0) (/ 1 0)))
; 结果为 2
```

例如这IR中:

HIR 会显示程序的结构和全部信息.

但在 MIR 阶段, 降级过程中, 会展开树结构, 对于 `(+ (/ 1 0) (/ 1 0)))`, 会展开为:

```
hh00:
  jmp seg00

seg00:
  a1 = 1
  a2 = 0
  if a2 == 0:
    jmp handler(divide-by-zero, k=seg03)
  else:
    jmp seg03(a1 / a2)

seg03[t1]:
  b1 = 1
  b2 = 0
  if b2 == 0:
    jmp handler(divide-by-zero, k=seg06[t1, _])
  else:
    jmp seg06(t1, b1 / b2)

seg06[t1, t2]:
  t3 = t1 + t2
  return t3

handler(effect, k):
  if effect == divide-by-zero:
    jmp k(1)
```

## 常用命令

```bash
# 运行测试（全部）
uv run python -m pytest tests/ -v --cov=qy --cov-report=term-missing

# 运行单个测试文件
uv run python -m pytest tests/test_register_vm.py -v

# 运行单个测试用例
uv run python -m pytest tests/test_register_vm.py::test_arithmetic -v

# Lint
uv run ruff check .
uv run ruff format .
uv run ty check .

# Lint 自动修复
uv run ruff check . --fix --unsafe-fixes && uv run ruff format .

# 运行 CLI
uv run qy run examples/hello.qy
uv run qy repl
uv run qy ast examples/hello.qy
uv run qy hir examples/hello.qy
uv run qy mir examples/hello.qy
uv run qy lir examples/hello.qy
uv run qy bytecode examples/hello.qy

# 构建
uv build
```

## 架构

目标管线（固定，不可变）：

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> VM (register by python)
                                                                          |           -> Other VM.
                                                                          -> LLVM IR -> build
```

## 技术栈

- Python >=3.12，使用 `uv` 管理依赖
- 依赖：lark（解析）、typer（CLI）、pygls（LSP）
- 工具：ruff（lint+format）、ty（类型检查）、pytest（测试）、commitlint（提交信息）

## 备注

不要创建除文档以外的 `*.md` 文件；文档只能放在 `docs/` 目录，且必须在 `docs/README.md` 中注册。所有设计文档都必须放在
`docs/`，并在 `docs/README.md` 中注册；不允许长期存在未注册的设计文档。

LANGUAGE.md 是细节无关的语言设计文档，仅包含语言设计.

## 工作建议

- subagent 保持在 3~5 个.
- 通过 `make tokens` 获取包概览，保持更新.
- 不要采用任何形式的短期方案, 以正确性, 统一性为正确追求.