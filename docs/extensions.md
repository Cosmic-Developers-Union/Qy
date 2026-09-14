# Qy 扩展机制

本文档定义 Qy 与宿主环境之间的边界与扩展模型。稳定语言语义以 `LANGUAGE.md`
为准；包结构以 `docs/package-structure.md` 为准。

## 1. 目标

- Qy 语言内核独立：`qy.core` / `qy.frontend` / `qy.ir` / `qy.analysis` /
  `qy.backend/vm/spec` 不得直接依赖宿主能力。
- 宿主支持保留，但必须经过统一扩展边界：文件系统、进程、Python 执行、
  测试基础设施等，一律建模为 **扩展（extension）**。
- 语言侧只看到普通的 module / operator；扩展的宿主实现细节不进入语言模型。

## 2. 扩展声明

扩展由 `qy.ext.ExtensionDescriptor` 描述，声明是纯数据：

| 字段 | 含义 |
| --- | --- |
| `name` | 扩展名，例如 `qy.ext.python` |
| `module_name` | 语言侧 `from <module_name> import ...` 的名字；loader-only 扩展为 `None` |
| `version` | 扩展版本 |
| `description` | 面向维护者的说明 |
| `capabilities` | 该扩展需要的宿主 capability（如 `python-exec`、`filesystem`） |
| `bindings` | 对外 binding：`name` / `kind` / `doc` / `signature` / `capabilities` |

`kind` 使用与 `OperatorKind` 相同的词汇（`pure` / `scope` / `control` /
`effect` / `meta`），`value` 表示常量 binding。工具链（analyzer / LSP）只能依赖
这些声明理解扩展算子，不得读取宿主实现。

## 3. 注册与装载

```python
from qy.ext import ExtensionDescriptor, ExtensionCapability, ExtensionBinding, register_extension

def module() -> StandardModule: ...

DESCRIPTOR = ExtensionDescriptor(
    name="qy.ext.example",
    module_name="qy.example",
    capabilities=(ExtensionCapability("network", "访问网络"),),
    bindings=(ExtensionBinding("fetch", kind="effect", capabilities=("network",)),),
)
register_extension(DESCRIPTOR, module)
```

- `qy.ext.register_extension` 只登记声明与模块工厂，不执行宿主能力。
- 模块系统把每个扩展的 `module_name` 注册为普通模块 loader；
  扩展模块只在显式 `from` 时装载（符合“host reference/operator 必须通过
  显式 import 进入 symbol-space-chain”）。
- `load_extension(name)` 供工具链检查模块内容；语言求值入口仍然是普通 import。

## 4. 宿主对象边界

- 宿主对象跨边界统一包装为 `qy.sem.host.HostReference`（语义层 runtime value）。
- VM instance 只重导出该类型（`qy.vm.instance.values.HostObjectRef` 为兼容别名）。
- 扩展负责创建/解包 host reference，并把宿主异常转换成语言级错误
  （`QyError` 子类），不得把宿主异常类型暴露给语言。
- 转换助手：`qy.sem.bridge.to_qy_value` / `from_qy_value`（宿主 primitive ↔
  `IntValue`/`FloatValue`/`StringValue`/容器语义值；未知对象 → `HostReference`）。
  仅限扩展边界调用；内核不得自动转换。legacy `to_sem`/`from_sem` 仍保留在
  同一模块用于迁移期。

## 5. 文件模块后缀

`.qy` 文件模块由内核直接加载（语言原生格式）。其他后缀（例如 `.py`）由扩展
通过 `qy.import_.registry.register_file_module_loader(suffix, loader)` 注册；
内核 `import_` 注册表不包含任何宿主文件格式逻辑。

## 6. 内置扩展

| 扩展 | module_name | capability | 说明 |
| --- | --- | --- | --- |
| `qy.ext.python` | `qy.py` | `python-exec` | `py`：执行内嵌 async Python |
| `qy.ext.python-modules` | —（loader-only） | `host-python-modules` | 把 `.py` 文件装载为 Qy 模块 |
| `qy.ext.fs` | `qy.ext.fs` | `filesystem` | `read-file` |
| `qy.ext.interp` | `qy.ext.interp` | `cli` / `introspection` / `symbols` | 自举解释器/工具链：`cli-args`、`lookup-export`、`display`、`raise-error`、`gensym` |
| `qy.ext.testhost` | `qy.testhost` | `filesystem` / `coverage` | 测试基础设施：目录/文件状态、run-file、覆盖率 |

标准 profile (`qy.core` + `qy.io`) 不预装任何宿主扩展。

## 7. 迁移状态

已完成：

- `qy.symbol_space.python` → `qy.ext.python`（`qy.py` 仍为模块名）。
- `qy.symbol_space.testhost` → `qy.ext.testhost`（`qy.testhost` 仍为模块名）。
- `read-file` 从 `qy.io` 移入 `qy.ext.fs`；`qy.io` 只保留语言 IO（`print`/`echo`）。
- `.py` 文件模块加载从 `qy/import_/registry.py` 移入 `qy.ext.python-modules`；
  内核 registry 只保留通用的 suffix loader hook。
- 自举解释器的通用宿主能力（`cli-args` / `lookup-export` / `display` /
  `raise-error` / `gensym`）从 `qy.testhost` 拆出为 `qy.ext.interp`，
  解释器不再依赖测试扩展。
- `HostObjectRef` 定义移入 `qy.sem.host`，VM instance 只重导出。
- `python_container_operators` 更名为 `container_operators`（Qy 语义容器）。
- 字符串字面量解析为 `StringValue`（不再是宿主 `str`）；Python 扩展在边界
  显式完成 `StringValue <-> str`、`NumberValue <-> int/float` 转换。
- `string-split` / `string->list` 返回 `TupleValue`（不再是宿主 tuple）；
  `append` 按语义容器选择 `ListValue`/`TupleValue`/chain。
- `parallel`/`all` 的 join 结果在 VM 内构造为 `TupleValue`（不再是宿主 tuple）。
- `len`/`get`/`has?`/`append`/`chain` 只接受语义容器（chain / `TupleValue` /
  `ListValue` / `DictValue` / `SetValue`），不再接受裸宿主容器。
- 语义容器 `TupleValue`/`ListValue`/`DictValue`/`SetValue` 提供宿主级 permissive
  `__eq__`（与 `NumberValue`/`StringValue` 一致），仅用于测试/调试，不影响 Qy 语义。

待迁移（登记于 `todo.md`）：

- 其余 Python 原生值（裸 `list` / `tuple` / `dict` / `set` / `bool` / `None`）
  作为 runtime value 的迁移期互操作，需逐步收敛到语义对象；字符串/数字已完成。
- `qy.project` 对宿主文件系统/进程的访问应逐步经由显式扩展 capability。
- CLI / testhost 之外的宿主机能（进程、网络、时钟）尚无扩展声明。
