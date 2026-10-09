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

未实现：effect / module / macro / 并行 opcode / 变参函数（`&rest`/`&body`）。emitter 遇到这些
会抛出 `LLVMUnsupportedError`（显式「后端不支持」诊断），而不是降成 nil 或产出非法 IR；
`cons`/`car`/`cdr` 的 ABI 已声明但未在 emitter 中使用。

## 当前覆盖与限制（实测）

`examples/qy/validation/` 中走通「IR → `llc` → `clang`(+libqy) → native」且输出与 register VM
一致的是 `00_host_arithmetic`、`02_symbol_space_let`、`03_functions_tail_call`、
`09_register_vm_tail_call`（4/10）；端到端由 `tests/test_llvm_backend.py` 覆盖
（缺 `llc`/`clang` 时自动跳过）。

已知限制（其余用例的失败原因）：

- **常量**：`_emit_load_host` 不支持 `Chain`（引用列表）与内嵌宿主代码的字符串
  （如 `"""return py_value + 1"""`），会抛
  `LLVMUnsupportedError: llvm backend does not support constant ...`；标量常量已由
  `qy/backend/scalars.py` 统一分类；
- **未支持的 opcode**：effect / module / macro / 并行 opcode（如 `DEFEFFECT` /
  `HANDLE` / `PERFORM` / `RESUME` / `DEFINE_MODULE`）会抛出
  `LLVMUnsupportedError`，并给出 opcode 名；`qy llvm` 在 CLI 层以
  `ClickException` 报告。此前这些 opcode 会把 effect 名写成 `%reg_<symbol>`
  这种非法 SSA 名（`llc: use of undefined value '%reg_ask'`），或静默降成 nil；
  现在统一为编译期显式失败；
- **未解析符号**：编译期未解析的符号（`==`、quasiquote / 宏 helper 等）发射为
  `qy_resolve_sym` 调用，而 libqy 当前对未知名字返回 nil；调用它以
  `qy_call: expected function, got tag 0` abort。这是 libqy 符号表覆盖不足，不是 IR
  生成缺陷；
- **多顶层结果显示**：LLVM 的 `@main` 只打印函数返回值（最后一个顶层结果），而
  `qy run` 打印所有 `APPEND_RESULT`（过滤 definition artifact）；多顶层程序因此
  输出行数不同（如 `05_define_once` / `40_eq_value_identity`）；
- **链接**：`llc` 必须用 `-relocation-model=pic`，否则对只读数据段的引用会生成
  32-bit 绝对重定位，默认 PIE 链接报 `R_X86_64_32` /
  `failed to set dynamic section sizes`（此前 `04_macro_hygiene` 的链接失败即此因）。
  `qy/backend/llvm/link.py` 与测试已固定该选项；
- **符号全局名**：`sym_global` 对非 `[A-Za-z0-9_.]` 字符做十六进制转义，因此
  `==`、`"hello"` 这类 spelling 不再生成非法 LLVM 标识符（原文仍存进数据段供
  `qy_resolve_sym` 解析）。

## 使用与验证

```bash
qy llvm examples/qy/validation/00_host_arithmetic.qy > program.ll
llc -relocation-model=pic -filetype=obj program.ll -o program.o
clang program.o qy/resources/libqy/src/runtime.o -o program
./program

# 或
make libqy
make llvm SRC=examples/qy/validation/03_functions_tail_call.qy RUN=1
make llvm-verify SRC=examples/qy/validation/00_host_arithmetic.qy
```

`tests/test_llvm_backend.py`：结构测试 + 端到端测试（需要 `llc` + `clang`，
否则跳过），把 IR 汇编链接后运行并与 register VM 结果对比。
