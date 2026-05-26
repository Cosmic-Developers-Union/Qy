# LIR Effect Frame Design

## 目标

把 `_EffectFrame` 从 register VM 运行时 Python 对象下沉到 LIR/bytecode 层，使 effect frame 的捕获与恢复成为编译时生成的指令序列，而非运行时动态 closure。

## 当前状态

**位置**：`qy/vm/instance/machine.py`

`_EffectFrame` 在 `PERFORM` 指令执行时捕获当前帧状态。

### LIR effect lowering 已实现

`qy/passes/lir/effects.py` 已实现从 effect placeholder 到 abstract machine ops 的 lowering：

- `EFFECT_HANDLE_BEGIN/END` → `HANDLER_PUSH` / `HANDLER_POP` + dispatch
- `EFFECT_PERFORM` → `CONT_CAPTURE` + `EFFECT_UNWIND`
- `EFFECT_RESUME` → `CONT_COPY` + `CONT_RESTORE`

配套数据结构已实现：

- `LIRHandlerLayout`：handler frame layout
- `LIRContinuationLayout`：continuation frame layout（含 multi_shot 标志）

LIR 指令集已包含抽象机器指令：

- `FRAME_ENTER` / `FRAME_LEAVE`
- `CONT_CAPTURE` / `CONT_COPY` / `CONT_RESTORE` / `CONT_INJECT`
- `HANDLER_PUSH` / `HANDLER_POP`
- `EFFECT_UNWIND` / `EFFECT_DISPATCH`
- `SS_ENTER` / `SS_LEAVE` / `SS_COPY` / `SS_RESTORE`
- `SLOT_READ` / `SLOT_COMPLETE` / `SLOT_PENDING_EFFORT`

### 剩余工作

1. bytecode compiler（`qy/backend/vm/compiler.py`）当前只做薄映射，尚未处理 abstract machine ops → bytecode 的转换
2. register VM（`qy/vm/instance/machine.py`）当前仍通过 Python `_EffectFrame` dataclass 实现 effect，尚未消费 LIR lowering 产出的 frame layout
3. `compat LIR` → `abstract-machine LIR` 的完全切换尚未完成

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

已通过 `TAIL_CALL` opcode 实现。

### 互递归

未实现。需要在 LIR 层检测跨函数的尾调用，生成蹦床化代码。

### Effect 边界下的尾调用

未实现。当 `perform` 在尾位置发生时，continuation 必须保留尾上下文。当前实现中 effect frame 捕获整个帧，语义正确但不够高效。

## 下一步

1. bytecode compiler 处理 abstract machine ops → bytecode 的转换
2. register VM 消费 LIR lowering 产出的 frame layout，替代 Python `_EffectFrame` dataclass
3. 完成 `compat LIR` → `abstract-machine LIR` 的切换
4. 实现互递归蹦床化
