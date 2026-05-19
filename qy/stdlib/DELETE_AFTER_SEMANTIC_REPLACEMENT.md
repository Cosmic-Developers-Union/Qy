# qy/stdlib 删除标记

`qy/stdlib/` 整个目录是迁移期兼容目录。

删除条件：
- 标准库能力迁移到 `qy/std/`。
- `std` 不再依赖 legacy evaluator helpers。
- profile/operator metadata 已进入 core/std/profile 统一模型。

标记：`QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/std/*`

