# LIR Effect Frame Design

## 目标

把 `_EffectFrame` 从 register VM 运行时 Python 对象下沉到 LIR/bytecode 层，使 effect frame 的捕获与恢复成为编译时生成的指令序列，而非运行时动态 closure。

## 当前状态

**位置**：`qy/register_vm.py` 第 49-64 行

`_EffectFrame` 是一个 frozen dataclass，在 `PERFORM` 指令执行时捕获当前帧的状态：

```python
@dataclass(frozen=True)
class _EffectFrame:
    registers: list[object]
    env: Environment
    pc: int
    parents: list[_ParentFrame]
    results: list[object]
    function_value: object
    function: BytecodeFunctionValue
```

当 `resume` 被调用时，一个 Python async closure 恢复帧状态并从 `pc+1` 继续执行。

## 设计

### 新 LIR 指令

| 指令 | 操作数 | 语义 |
| --- | --- | --- |
| `SAVE_FRAME` | `dest_reg` | 将当前帧状态（registers、env、pc）保存到 dest_reg |
| `RESTORE_FRAME` | `src_reg` | 从 src_reg 恢复帧状态，继续执行 |

### ABI

- `SAVE_FRAME` 产出一个 host value（等价于当前 `_EffectFrame`），存入 dest_reg
- `RESTORE_FRAME` 消费该 host value，恢复执行到 save 点的下一条指令
- `PERFORM` 的 handler 接收 `SAVE_FRAME` 产出的 frame value 作为 continuation 的底层表示

### 编译时 lowering

`mir_lowering.py` 中 `PERFORM` 的 lowering 改为：

```
SAVE_FRAME r_frame          ; 捕获当前帧
PERFORM r_result, effect, r_arg  ; 执行效应
```

handler 函数接收 continuation（即 frame value），`resume` 的 lowering 改为：

```
WRITE_REG r_resumed, r_value  ; 设置恢复值
RESTORE_FRAME r_frame         ; 跳回 save 点
```

### 阻塞点

1. **`mir.py`（冻结文件）**：需要新增 `SAVE_FRAME` / `RESTORE_FRAME` MIROpcode
2. **`bytecode.py`**：需要新增对应 Opcode
3. **`register_vm.py`（冻结文件）**：需要新增指令处理器

在不修改冻结文件的前提下，此设计只能作为规范文档存在，无法直接实现。

## parallel / all / race 与 effect 合流

### parallel

每个分支在独立 task 中执行。若某分支 perform effect：

- continuation 仅在该分支 task 内有效
- 其他分支不受影响
- 当前实现（`asyncio.gather`）正确

### all

屏障语义——所有分支必须完成后父级才恢复。若某分支 perform effect：

- handler 看到该 effect
- 但屏障仍等待所有分支完成
- 当前实现正确（`asyncio.gather` 天然等待所有）

### race

first-resume-wins——第一个 resume 的分支胜出，其他分支被取消。若某分支 perform effect：

- handler 处理该 effect 并 resume
- 第一个 resume 的分支使 race 完成
- 其他分支应被取消
- 当前实现（`asyncio.wait(FIRST_COMPLETED)`）需要验证取消行为

## 虚拟栈与尾调用

### 自尾递归

已通过 `TAIL_CALL` opcode 实现。VM 在 `register_vm.py` 第 249-255 行检测自我尾调用并重用当前帧。

### 互递归

未实现。需要在 LIR 层检测跨函数的尾调用，生成蹦床化代码。

### Effect 边界下的尾调用

未实现。当 `perform` 在尾位置发生时，continuation 必须保留尾上下文。当前实现中 effect frame 捕获整个帧，语义正确但不够高效。

## 下一步

1. 解冻 `mir.py` 时，新增 `SAVE_FRAME` / `RESTORE_FRAME` opcode
2. 在 `lir_lowering.py` 中实现 PERFORM 的 frame save lowering
3. 在 `register_vm.py` 中实现新指令处理器
4. 迁移 `_EffectFrame` 从 Python dataclass 到 LIR 指令序列
