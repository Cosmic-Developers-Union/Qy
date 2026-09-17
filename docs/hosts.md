# 多宿主（Python / TypeScript / Go）

本文档定义 Qy 作为**嵌入式语言**在不同宿主语言中的工作方式与实现边界。
语言语义以 `LANGUAGE.md` 为准；包结构以 `docs/package-structure.md` 为准；
宿主扩展与 capability 模型见 `docs/extensions.md`。

## 1. 目标与范围

| 宿主 | 解释执行（VM 跑字节码） | 编译后端 | 宿主语言扩展 |
| --- | --- | --- | --- |
| Python | ✅ `RegisterVirtualMachine`、`Qy.run_bytecode_json`、`qy run --bytecode` | ✅ Python VM 字节码 / LLVM IR / WASM | ✅ `qy.ext`（descriptor + registry + capability） |
| TypeScript / JavaScript | 见 §5 现状 | 复用同一份字节码 JSON；WASM 由 Python 侧产出 | 见 §5 现状 |
| Go | 见 §5 现状 | 复用同一份字节码 JSON | 待实现 |

开发顺序：**Python 与 TypeScript 先行，Go 后续**。

## 2. 架构：编译一次，多宿主执行

```text
.qy 源码
  └─(Python 侧编译器)─> 字节码 BytecodeProgram
        ├── 直接由 Python 虚拟机执行（qy run / Qy.evaluate_*）
        └── qy export FILE -o prog.json
              ├── Python：Qy.run_bytecode_json / qy run --bytecode
              ├── TypeScript：qyvm prog.json
              └── Go：qyvm prog.json
```

要点：

- 编译器只有一份（Python 侧），其它宿主只实现**虚拟机**，不重复实现前端/中端；
- 交换格式是唯一的跨宿主契约，见 §3；
- 各宿主的标准算子实现可以不同（Python 委托给 `qy.std`/`qy.session`，TS/Go 各自实现），
  但**内建算子的名字、ABI 元数与下标顺序**由 `qy/core/operator_builtins.py`
  统一规定（`CALL_BUILTIN` 的下标即该表顺序）。

## 3. 字节码交换格式（契约）

- 编码：`qy/backend/vm/bytecode.py::serialize_bytecode_json`；
- 解码（对端语义）：同文件 `load_bytecode_json` —— **它就是其它宿主必须实现的装载语义**；
- 顶层字段：`version`(=1)、`main`、`functions[{name, params, register_count,
  instructions[{opcode, operands}]}]`、可选 `hygiene_bindings`；
- 操作数类型：`reg` / `int` / `float` / `bool` / `string` / `symbol` / `nil` / `t` /
  `none` / `chain` / `effect_def` / `reg_tuple` / `handler_specs` / `import_specs` /
  `symbol_tuple` / `list` / `tuple` / `binding_addr`（`{"space","slot"}`，abstract-machine
  方言的 `SLOT_COMPLETE` 用）；
- Qy 语义值编码为 `{type, class, value}`（`class` 为 `qy/sem/core.py` 中的值类名，
  `value` 是该 dataclass 的字段字典），`nil` / `T` / `none` 保持单例；
- 无法编码的值必须**显式报错**，不得退化成 `{"type":"unknown"}`（历史上曾把
  `IntValue(2)` 编码成 repr 字符串，装载后变成 `str`，运行期报类型错误）；
- 交换格式还必须自带运行期所需的两类元数据（否则程序在新环境下跑不起来）：
  - `hygiene_bindings`：卫生宏别名 → 目标名，装载侧必须装成**惰性别名**
    （`qy.core.symbol_space.SymbolAlias`：目标可能在本程序稍后才定义）；
  - `module_macro_exports`：模块名 → 编译期宏导出名；运行期这些名字没有绑定值，
    `from` 命中时应跳过绑定而不是报「模块没有该导出」；
  - `symbol_spaces`：程序级符号空间 layout（`id` / `name` / `parent` /
    `slots[{symbol,index,source}]`），装载时同时挂到每个函数上——VM 的
    `SLOT_COMPLETE` 读 `frame.function.symbol_spaces` 才能把
    `binding_addr` 还原成 symbol；
- **整数必须精确**：JSON 用十进制字符串/精确解析器读写，任何一侧用 double 中转都会在
  2^53 之后静默丢精度（TypeScript 用自写精确 JSON 解析器，Go 用 `UseNumber`）。

两条硬性要求（由 `tests/test_bytecode_json.py` 守卫）：

1. **可表示**：程序里每个常量都能编码；
2. **可还原**：装载后执行的结果与直接执行编译产物完全一致
   （`tests/qy` 全部 55 个程序逐字节一致）。

## 4. 宿主扩展与值转换

- 宿主对象进入语言统一包装为 `qy.sem.host.HostReference`；
- 值转换的唯一实现在 `qy/sem/convert.py`（`to_qy_value` / `from_qy_value`），
  扩展与嵌入式宿主共用，内核不自动转换；
- capability 准入由 `qy.ext.ExtensionPolicy` 负责（见 `docs/extensions.md`）。

Python 嵌入式 API（`qy.runtime`）：`Qy` / `AsyncQy`、`evaluate_source` /
`evaluate_program` / `evaluate_file`、`run_bytecode_json`、
`call(function, *args)`（调用 Qy 函数值）、`register_pure`、`env.define` / `env.child`。

## 5. 现状与差距（实测）

**Python**：解释执行与三种编译后端齐备。LLVM 原生链路的覆盖与限制见
`docs/llvm-backend.md`；WASM 链路为 `qy wasm` → `wat2wasm` → `node
qy/resources/wasm/runtime.js`（`tests/test_wasm_backend.py`，缺工具链时跳过）。

**TypeScript / JavaScript**：已实现，目录 `qy/backend/typescript/`，TypeScript 编写、
零运行时依赖、以 `bun` 运行。入口 `bun bin/qyvm.ts prog.json`；嵌入式 API 在
`src/embed.ts`（`createVm` / `evalBytecode` / `registerHostFunction`）。

实测（bun 1.3.14）：`bun scripts/conformance.ts` → **55/55**（与 Python 虚拟机逐字节一致）；
`bun test` → **34 pass / 0 fail**。

实测（bun 1.3.14，语料 `tests/qy` 共 55 个）：

```bash
cd qy/backend/typescript && bun test                                    # 48 pass
bun qy/backend/typescript/scripts/conformance.ts                        # compat 55/55
bun qy/backend/typescript/scripts/conformance.ts --dialect abstract-machine  # 55/55
bun qy/backend/typescript/scripts/bigint_conformance.ts                 # 13/13
```

- **整数为任意精度**（`bigint` + 自写精确 JSON 解析器），语义逐条对齐
  `qy/session/number_ops.py`（含二元除法异号时 Python 的 `int(a/b)` float 路径）；
- **并发**：`PARALLEL_GATHER`/`ALL_GATHER` 用 `Promise.allSettled`（保序），`RACE_FIRST`
  用 `Promise.race`；前置保守纯度判定，遇 effect/continuation/handler/共享状态写入/IO
  内建/嵌套 gather 时整批回退顺序执行；宿主函数支持 async；
- 已知限制：`RUNTIME_EVAL` 只支持 Symbol 解析 / `quote` / 已解析算子的 eager 调用
  （special form、宏、`define`、`perform` 等需要编译期的形式不支持，不引入第二套语义）；
  纯同步 thunk 的 `race` 胜者在 JS 与 Python asyncio 下可能不同（有真实 async 调用时
  两者都是最快者胜）；`tsconfig.json` 声明 `bun-types` 但未安装（零依赖约束，未启用
  tsc 检查）。

**Go**：已实现。`go.mod` 在仓库根（module `github.com/Cosmic-Developers-Union/Qy`，
零第三方依赖），`qy/backend/golang/` 与 `go-reader/` 同属一个 module；入口
`go run ./qy/backend/golang/cmd/qyvm prog.json`。嵌入式 API 在 `examples/go/qyhost`
（宿主算子注册/同名覆盖/接管输出）。

整数为**任意精度**（`math/big.Int`；JSON 用 `UseNumber()` 精确解析，2^53 之后不丢精度），
语义逐条对齐 `qy/session/number_ops.py`（含二元除法异号时 Python 的 `int(a/b)` float
路径）；两种 LIR 方言均支持（`SLOT_COMPLETE` 经 `symbol_spaces` layout 还原 symbol）。

实测（go1.27，语料 `tests/qy` 共 55 个）：

```bash
export GOCACHE=$(mktemp -d)          # 仅在默认 GOCACHE 只读的环境需要
go build ./... && go vet ./... && go test ./...
bash qy/backend/golang/conformance.sh                            # → passed 55/55
bash qy/backend/golang/conformance.sh --dialect abstract-machine  # → passed 55/55
bash qy/backend/golang/bigint_conformance.sh                      # → passed 13/13
go run ./examples/go/hello                                        # → 42
```

已知限制：`PARALLEL_GATHER`/`ALL_GATHER` 顺序执行且只返回首个错误（Python 的
`PARALLEL_GATHER` 会聚合为 `QyAggregateError`）、`RACE_FIRST` 取第一个 thunk；
`CACHE_EVAL` 用 VM 全局 map + `FormatValue(key)` 作为键；`EFFECT_UNWIND` 强类型要求
`*Continuation`（Python 对非 continuation 默认 `resumable=true`）；`read`/`read-int`
内建返回 nil（未接 stdin）；`CoerceHostNumber` 沿用 TS 的"整数值宿主 float64 → IntValue"
启发式（Python 对宿主 float 一律 FloatValue）；`RUNTIME_EVAL` 是极简 eager 解释器
（Go 宿主不含编译器）。

## 6. 验收标准

1. **同源一致**：同一个 `.qy` 文件在任一宿主 VM 上的输出与 Python 虚拟机逐字节一致
   （语料 `tests/qy/*.qy`，共 55 个；扩展语料 `meta-interp/cases/*.qy`）。Python 侧由
   `tests/test_bytecode_json.py` 守卫（在**全新环境**执行装载结果，并端到端跑
   `qy export` + `qy run --bytecode`）；TypeScript 侧由
   `bun qy/backend/typescript/scripts/conformance.ts` 守卫；
2. **格式契约**：§3 的两条硬性要求始终成立；
3. **自举**：`meta-interp/main.qy`（Qy 写的 Qy 解释器）对上 `meta-interp/cases/*.qy`
   全部用例（`bash meta-interp/compare.sh` → 19/19），并能解释自身
   （`QY_META_SELF=1 pytest tests/test_meta_interp.py`，当前通过）。两者由
   `make test-selfhost` 统一验证，并已纳入 `make ci`。已实现的宏 hygiene：
   binder 重命名 + 定义点自由符号 + `capture`/`gensym`；
4. **effect 一致**：代数效应的可观察行为跨宿主一致（`docs/roadmap.yaml` 要求）。
   已实现宿主的上限由各自的 conformance 命令守卫：`make test-ts`（TypeScript）、
   `make test-go`（Go）、`tests/test_bytecode_json.py` + `qy run --bytecode`（Python）。
