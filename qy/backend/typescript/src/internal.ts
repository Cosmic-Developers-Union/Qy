// VM 内部哨兵。
//
// `MISSING` 对应 Python `qy.core.symbol_space.MISSING`：符号空间查找/字面量解析
// 的"未命中"标记，必须与任何 Qy 值（包括 nil）都不同。

export const MISSING: unique symbol = Symbol('qy.missing');
export type Missing = typeof MISSING;
