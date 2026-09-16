# Stdlib Operator Draft

本文档记录标准库算子的当前设计草案。它不是语言规范，也不是核心语义来源；非核心算子可以频繁调整。  
稳定语言语义以 `LANGUAGE.md` 为准，核心 form 以 `docs/op.md` 为准。

## 原则

- 算子不是语言设计重点；先保证 symbol-space、effect、IR/VM、macro 等核心模型稳定。
- 新增算子前先判断它能否由 Qy 自身实现：
  - 能由 Qy library 组合出的能力，优先写成 Qy；
  - 只有 runtime primitive、文件系统、宿主桥接等无法由 Qy 自举的能力，才下沉为 host operator。
- 标准库分两层：
  - **host primitive**：标准实现必须提供的最小原语；
  - **Qy library**：用核心 form 与 host primitive 组合出的派生能力。
- `eq` 始终保留 Lisp identity 语义；数值相等、字符串相等、结构相等必须分别建模。
- 下列名称均为工作草案，可随实现推进调整。

## 数值库草案

建议 namespace：`qy.num`

### Host primitive

| 算子            | 说明                             |
| --------------- | -------------------------------- |
| `number?`       | 判断 runtime value 是否为 number |
| `+`             | 加法                             |
| `-`             | 减法；一元时取负                 |
| `*`             | 乘法                             |
| `/`             | 除法；一元时取倒数               |
| `=`             | 数值相等                         |
| `<`             | 严格小于                         |
| `remainder`     | 余数                             |
| `string->number` | 解析数字字面量字符串；失败返回 `nil` |

### Qy library

| 算子        | 可由哪些原语定义   |
| ----------- | ------------------ |
| `<=`        | `<` + `=`          |
| `>`         | `<`                |
| `>=`        | `<` + `=`          |
| `zero?`     | `=`                |
| `positive?` | `<`                |
| `negative?` | `<`                |
| `inc`       | `+`                |
| `dec`       | `-`                |
| `abs`       | `<` + `cond` + `-` |
| `even?`     | `remainder` + `=`  |
| `odd?`      | `remainder` + `=`  |
| `min`       | `<` + `cond`       |
| `max`       | `<` + `cond`       |

### 暂缓

| 模块      | 算子                                                  |
| --------- | ----------------------------------------------------- |
| `qy.math` | `pow` `sqrt` `floor` `ceil` `round` `sin` `cos` `log` |

说明：

- `=` 只负责 number equality，不替代 `eq`。
- `==` 不应继续作为正式 Qy 语义扩张点；若保留，只能算兼容层遗留。

## 字符串库草案

建议 namespace：`qy.str`

### 设计前提

- 这里操作的是 runtime `string`，不是 syntax `symbol`。
- 不应再沿用“无法求值的 symbol 自动当文本”的旧行为。
- `str-*` 旧 family 只代表当前兼容实现，不代表目标 API。

### Host primitive

| 算子             | 说明                             |
| ---------------- | -------------------------------- |
| `string?`        | 判断 runtime value 是否为 string |
| `string-length`  | 字符串长度                       |
| `string-concat`  | 拼接                             |
| `string=`        | 字符串相等                       |
| `string-slice`   | 切片                             |
| `string-at`      | 取单个位置                       |
| `string-find`    | 查找子串                         |
| `string-split`   | 分割                             |
| `string-join`    | 连接                             |
| `string-replace` | 替换                             |

### Qy library

| 算子                  | 可由哪些原语定义                             |
| --------------------- | -------------------------------------------- |
| `string-empty?`       | `string-length` + `=`                        |
| `string-starts-with?` | `string-slice` + `string=`                   |
| `string-ends-with?`   | `string-length` + `string-slice` + `string=` |

### 可选 host extension

| 算子           | 说明         |
| -------------- | ------------ |
| `string-upper` | Unicode 大写 |
| `string-lower` | Unicode 小写 |
| `string-trim`  | 两端裁剪     |

说明：

- `string-upper` / `string-lower` / `string-trim` 涉及宿主 Unicode 行为，可以作为 stdlib host extension，但不是最小能力。
- `show` / `display` / `repr` 若以后需要，应作为单独文本化能力设计，不与 runtime string 本体混淆。

## IO 草案

建议 namespace：`qy.io`。IO 属于"无法由 Qy 自举"的宿主能力，允许作为 host primitive 存在。

| 算子        | 类型     | 说明                                                         |
| ----------- | -------- | ------------------------------------------------------------ |
| `print`     | effect   | 打印求值后的值，返回最后一个打印值                           |
| `echo`      | effect   | `print` 别名                                                 |
| `read-file` | effect   | 读取文本文件并返回 `string`；参数为路径（symbol 或 string） |

说明：

- `print` / `echo` 是 raw-argument 算子：字面量实参以 syntax datum（symbol）形式到达，需在宿主边界解析为 runtime value；已经求值完成的复合实参（chain 等）**不得再次求值**。
- `read-file` 的路径参数允许 symbol 或 string；文件系统访问失败进入语言级错误路径。

## 结构相等

`eq` 不能承担结构相等。若测试框架或 stdlib 需要结构比较，后续另行设计：

| 候选     | 说明                                                |
| -------- | --------------------------------------------------- |
| `equal?` | 结构相等，覆盖 immutable chain 与必要 runtime value |

`equal?` 是否进入 stdlib、由 Qy 实现还是由 host 辅助，待 chain/runtime value 边界稳定后再决定。

## 当前状态

标准库实现位于 `qy/std/`（历史 `qy/stdlib/` shim 已删除），把 `StandardModule` /
`register_module` / `LANGUAGE_CORE_MODULES` / `PRELUDE_MODULES` /
`STANDARD_PROFILE_MODULES` / `OPTIONAL_STDLIB_MODULES` 等从 `qy.std`
re-export。`qy.std` 是当前实际承载标准库算子（`qy.num` / `qy.str` /
`qy.char` / `qy.io` 等）的目标包。

历史 `qy.stdlib.arithmetic` / `qy.stdlib.strings` 子模块已不存在；
`+ - * /` 等数值算子由 standard profile（`qy/std/numeric_spaces.py` +
profile 注册表）直接预装进 `pre-symbol-space-chain`，字符串算子由
`qy.std.strings` 承载，不再走旧的 `str-*` family。

下一步应先完成 runtime `string` 与 `pre-symbol-space-chain` 的正式模型
（见 `todo.md` Phase D 与 Phase M），再按本草案重写字符串库；不要在旧
`str-*` family 上继续扩展。
