# Qy Examples

这里的示例按用途分层：

- `validation/`：当前实现应当可以运行的验证集。每个文件返回一个稳定结果，由 `run_validation.py` 检查。
- `design/`：语言目标示例，用来描述尚在落地中的核心语义。不要把这里的文件当成当前 runtime smoke test。
- `host/`：宿主注入 symbol-space、host object/operator 的 Python 示例。

验证当前示例：

```shell
uv run python examples/run_validation.py
```

调试单个阶段：

```shell
uv run python -m qy ast examples/validation/01_quote_chain.qy
uv run python -m qy expand examples/validation/04_macro_hygiene.qy
uv run python -m qy hir examples/validation/05_effect_resume.qy
uv run python -m qy mir examples/validation/09_register_vm_tail_call.qy
uv run python -m qy bytecode examples/validation/09_register_vm_tail_call.qy
```

当前语言目标见 `LANGUAGE.md`。示例必须避免继续把 `list`、`tuple`、`dict`、`str-*`、`spawn`、`await` 当成语言核心。
