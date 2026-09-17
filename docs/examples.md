# Qy 示例

示例按**宿主语言**分目录；每个目录都是该宿主下"如何使用 Qy"的可运行样例。

| 目录 | 内容 | 运行方式 |
| --- | --- | --- |
| `examples/qy/` | Qy 语言源码示例 | `uv run qy run examples/qy/hello.qy` |
| `examples/qy/validation/` | 当前实现应当可以运行的验证集（每个文件返回稳定结果，由 `examples/py/run_validation.py` 检查） | `uv run python examples/py/run_validation.py` |
| `examples/qy/design/` | 语言目标示例，描述尚在落地中的核心语义；**不是** runtime smoke test | 需人工阅读 |
| `examples/py/` | Python 宿主示例（注入 symbol-space、bytecode dump/序列化、验收脚本） | `uv run python examples/py/<file>.py` |
| `examples/ts/` | TypeScript 宿主示例：`hello.ts`（最小执行）、`host_functions.ts`（宿主函数注册/覆盖/输出接管）、`embed_api.ts`（嵌入式 API 与错误处理） | `bun examples/ts/run_all.ts` |
| `examples/go/` | Go 宿主示例：`hello`（最小执行）、`host_functions`（宿主算子注册/覆盖/接管输出）、`run_all` | `go run ./examples/go/run_all` |

`examples/qy/hello.qy` 是核心标准样例（golden file）：由人工维护、agent 不得修改，
所有工具链都必须接受它（见 `docs/roadmap.yaml`）。

验证示例：

```shell
make examples                                   # 全部示例（Python + TypeScript + Go 宿主）
uv run python examples/py/run_validation.py     # 仅 Qy 验收集
bun examples/ts/run_all.ts                      # 仅 TypeScript 宿主示例（需要 bun）
```

调试单个阶段：

```shell
uv run python -m qy ast examples/qy/validation/01_quote_chain.qy
uv run python -m qy expand examples/qy/validation/04_macro_hygiene.qy
uv run python -m qy hir examples/qy/validation/05_effect_resume.qy
uv run python -m qy mir examples/qy/validation/09_register_vm_tail_call.qy
uv run python -m qy bytecode examples/qy/validation/09_register_vm_tail_call.qy
```

当前语言目标见 `LANGUAGE.md`。示例必须避免继续把 `list`、`tuple`、`dict`、`str-*`、
`spawn`、`await` 当成语言核心。
