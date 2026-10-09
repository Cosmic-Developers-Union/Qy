# WebAssembly Backend

`qy/backend/wasm/` 把 register VM 的 **compat LIR** 降到 WebAssembly text（WAT），
由 `wat2wasm` 汇编后交给 Node 的 WebAssembly 引擎执行。宿主 runtime 在
`qy/resources/wasm/runtime.js`。

它和 LLVM 后端一样是**并行验证后端**：不取代 register VM，`qy run` /
`qy bytecode` / qytest 仍是默认执行路径。

## 管线位置

```text
source -> ... -> HIR -> MIR -> LIR(compat) -> WAT -> wasm -> Node WebAssembly
```

`qy wasm FILE` 只做到 WAT 输出；汇编与执行由外部工具完成。

## 值编码

值统一是 wasm `i64`，低 3 位 tag：

| tag | 含义 | 编码 |
| --- | --- | --- |
| 0 | int | `(value << 3) \| 0`（61-bit signed） |
| 1 | nil | 常量 `1` |
| 2 | T | 常量 `2` |
| 3 | char | `(codepoint << 3) \| 3` |
| 4 | callable | `(table_index << 3) \| 4` |
| 5 | string | `(data_offset << 3) \| 5`，linear memory 中 `[i32 len][utf8]` |
| 6 | float | `(data_offset << 3) \| 6`，f64 存于 linear memory（常量在数据段，结果在 bump arena） |
| 7 | heap | `(data_offset << 3) \| 7`，heap 对象首 i32 是子 tag：`1` symbol、`2` cons |

## 调用约定

所有可调用目标共享 wasm 类型：

```wat
(type $qyfn (func (param i32 i32) (result i64)))
;; param 0 = argc, param 1 = argv（linear memory 中连续 i64 参数区）
```

函数表布局：`[0, NUM_BUILTINS)` 是内建算子 trampoline（转调 JS 宿主的
`call_builtin`），之后是编译出的 Qy 函数（`table_index = NUM_BUILTINS + fn_idx`）。
动态调用用 `call_indirect`；`argv` 写在 linear memory 的 scratch 栈上，
用 `$sp` 维护（调用前后保存/恢复）。

## 控制流

LIR 是扁平 CFG，wasm 需要结构化控制流。emitter 用经典的
`loop` + `br_table` dispatcher：`pc` 是 i32 局部变量，每个指令索引对应一个
嵌套 `block`，`br_table` 的第 `i` 个目标恰好落在第 `i` 条指令的代码起点。

## 符号解析

`LOAD_ENV` 在**编译期**解析，优先级：

1. 参数 / 当前 scope 内由 `STORE_LOCAL` / `DEFINE_ONCE` 绑定的符号
   （快照进专用局部变量 `$eN`，避免被后续寄存器复用覆盖）；
2. 函数自身名（支持直接自递归）；
3. `nil` / `T` / `false` / `true`；
4. 内建算子名（`BUILTIN_NAMES` 顺序见 `backend/wasm/abi.py`）；
5. 整数拼写。

其余符号（模块 / 宿主绑定、闭包捕获的自由变量）会抛
`WasmUnsupportedError`，而不是静默编译成错误结果。

## 支持范围

已支持：int/nil/T/string/float 值，`+ - * / = eq < >`（float 走 f64 语义），symbol 与 chain
（heap 对象，`cons`/`car`/`cdr`、quote 数据、嵌套/点对链），无自由变量的
`defun`/`lambda`，`let`，`cond`/`pipeline` 控制流，`CALL` / `TAIL_CALL`
（尚未做尾调用优化），`display`/`echo`/`newline`（由宿主提供；raw-argument 字面量实参
如 `(display 1)` 在编译期按实例字面量规则折成 value）。

未支持（遇到即报错）：effect（`defeffect`/`perform`/`handle`/`resume`）、
module/import、macro、`parallel`/`all`/`race`、`apply`/`build-tuple`/`tuple`、
变参函数（`&rest`/`&body`）、闭包捕获、深尾递归（无 TCO）。

## 使用

```bash
qy wasm examples/qy/validation/00_host_arithmetic.qy > program.wat
wat2wasm program.wat -o program.wasm
node qy/resources/wasm/runtime.js program.wasm
```

## 验证

`tests/test_wasm_backend.py`：

- 纯结构测试（WAT 结构、不支持 opcode 抛错、非 compat dialect 拒绝）；
- 端到端测试（需要 `wat2wasm` + `node`，否则跳过）：把 WAT 汇编后交给
  Node 执行，结果与 register VM 一致。

## 与 LLVM 后端的关系

两者消费同一份 compat LIR，共享同一套 `BUILTIN_NAMES` 顺序与 tag 语义。
WASM 后端用 i64 标量编码，不需要 libqy 的 `struct qy_value` 内存布局；
因此它不依赖 `qy/resources/libqy`，宿主 runtime 是纯 JS。
