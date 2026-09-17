# LLVM Backend

`qy/backend/llvm/` 把 register VM 的 **compat LIR** 降到 LLVM IR（文本），
与 `qy/resources/libqy/`（C runtime，`qy.h` + `runtime.c`）链接后可生成
原生可执行文件。它是**并行验证后端**：不取代 register VM。

## 管线位置

```text
source -> ... -> HIR -> MIR -> LIR(compat) -> LLVM IR -> llc -> clang(+libqy) -> native
```

`qy llvm FILE` 只输出 LLVM IR 文本；汇编与链接由 `make llvm` / `llc` / `clang`
完成。

## 值布局与 C ABI

`%qy_value` 与 `qy.h` 的 `qy_value` 完全一致：

```llvm
%qy_value = type { i8, [7 x i8], [3 x i64] }   ; 32 bytes, align 8
```

关键点：32-byte 结构体在 x86-64 SysV 上**不是按值传参/返回**，而是

- 返回：`ptr sret(%qy_value) align 8`（隐藏返回指针，作为第 0 个参数）；
- 传参：`ptr byval(%qy_value) align 8`。

emitter 的所有 `qy_*` 声明以及编译出的 `qy_fn_N` 都使用这套签名，并通过
opaque pointer（`ptr`）书写。这与 clang 为 `qy.h` 生成的 ABI 逐字一致；
早期版本直接写 `%qy_value` 按值传参，链接后会在运行时读错 tag。

## 寄存器与符号

- 每个 LIR 寄存器是 entry block 里的 `alloca %qy_value`；def/use 都走内存，
  因此任意 CFG 都不需要 SSA phi / dominance 处理。
- LIR 是扁平 CFG，但 LLVM 支持任意基本块，所以每个指令索引直接对应
  `block_N`，无需 wasm 那样的 dispatcher。
- `LOAD_ENV` 在编译期解析：参数 / `STORE_LOCAL` / `DEFINE_ONCE` 绑定快照进
  `%env_N` alloca；函数自身名支持直接自递归；数字字面量内联构造
  `%qy_value`（`insertvalue`）；内建算子走 `qy_builtin_fn`；其余符号走
  `qy_resolve_sym`（libqy 当前返回 nil）。

## 模块契约

libqy 的 `qy_main_c` / `qy_call` 依赖：

- `@qy_fn_table`：`[N x ptr]`，元素是 `qy_fn_N` 的函数指针；
- `@qy_fn_table_size`：`constant i64 N`；
- `@qy_main`：`qy_fn_<main>` 的包装；
- 本模块自己的 C `@main`：调用 `qy_init`，运行 `qy_fn_<main>`，用
  `qy_println` 输出顶层结果。

## 支持范围

已支持：int/nil/T/string、内建算术/比较、无自由变量的 `defun`/`lambda`、
`let`、`cond`/`pipeline` 控制流、`CALL`/`TAIL_CALL`（尚无 TCO）。

占位：effect / module / macro / 并行 opcode 目前降成 nil，保持 IR 有效；
`cons`/`car`/`cdr` 的 ABI 已声明但未在 emitter 中使用。

## 当前覆盖与限制（实测）

`examples/qy/validation/` 中走通「IR → `llc` → `clang`(+libqy) → native」且输出与 register VM
一致的是 `00_host_arithmetic`、`02_symbol_space_let`、`03_functions_tail_call`、
`09_register_vm_tail_call`（4/10）；端到端由 `tests/test_llvm_backend.py` 覆盖
（缺 `llc`/`clang` 时自动跳过）。

已知限制（其余用例的失败原因）：

- **常量**：`_emit_load_host` 不支持 `Chain`（引用列表）与内嵌宿主代码的字符串
  （如 `"""return py_value + 1"""`），会抛
  `ValueError: llvm backend does not support constant ...`；标量常量已由
  `qy/backend/scalars.py` 统一分类；
- **未解析符号**：effect 名、模块名等符号会被发射成引用未定义 SSA 值
  （`llc: use of undefined value '%reg_ask'` / `'%reg_<module>'`），需要在这些值上
  给出明确的「后端不支持」诊断，而不是产出非法 IR；
- `04_macro_hygiene` 在链接阶段报 `ld: failed to set dynamic section sizes`，
  属当前环境的链接器行为，需进一步确认。

## 使用与验证

```bash
qy llvm examples/qy/validation/00_host_arithmetic.qy > program.ll
llc -filetype=obj program.ll -o program.o
clang program.o qy/resources/libqy/src/runtime.o -o program
./program

# 或
make libqy
make llvm SRC=examples/qy/validation/03_functions_tail_call.qy RUN=1
make llvm-verify SRC=examples/qy/validation/00_host_arithmetic.qy
```

`tests/test_llvm_backend.py`：结构测试 + 端到端测试（需要 `llc` + `clang`，
否则跳过），把 IR 汇编链接后运行并与 register VM 结果对比。
