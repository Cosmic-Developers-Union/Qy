# Qy 支持的算子

## 内建算子

模块：`qy.core`

- `*` - 纯算子：数字相乘。
- `+` - 纯算子：数字求和。
- `-` - 纯算子：数字相减；单参数时取负。
- `/` - 纯算子：数字相除；单参数时取倒数。
- `==` - 纯算子：按 Python == 语义比较两个值。
- `assert` - Effect 算子：断言 debug 条件；失败时执行 assert-failed。
- `assert-failed` - Effect 定义：assert 失败产生的不可恢复 effect。
- `atom` - 纯算子：如果值不是非空 chain 或 tuple，则返回 true。
- `await` - Effect 算子：等待一个或多个异步值。
- `cache` - Effect 算子：缓存一个表达式的求值结果。
- `car` - 纯算子：返回 chain 的第一个元素。
- `cdr` - 纯算子：返回 chain 除第一个元素外的剩余部分。
- `chain` - 纯算子：把 Python list/tuple 转换为 Qy chain。
- `component` - 作用域算子：在当前作用域定义可复用组件。
- `cond` - 控制算子：求值第一个 truthy 条件分支。
- `cons` - 纯算子：构造 chain cell；对 Python tuple/list 保持同类拼接。
- `defeffect` - 作用域算子：声明 effect，供 perform/handle 和分析器使用。
- `defun` - 作用域算子：在当前环境定义函数。
- `dict` - 纯算子：把 key/value 参数转换为 Python dict。
- `dict?` - 纯算子：判断值是否为 dict。
- `eq` - 纯算子：Lisp 风格 eq；chain 按 identity 比较。
- `eval` - 元算子：求值一个符号 form。
- `from` - 作用域算子：从模块导入算子到当前作用域。
- `get` - 纯算子：从 chain/tuple/list/dict 获取项。
- `handle` - 控制算子：处理表达式产生的 effect。
- `has?` - 纯算子：判断 collection 是否包含 key、index 或成员。
- `is` - 纯算子：按 Python is 语义比较 identity。
- `lambda` - 作用域算子：创建匿名函数。
- `len` - 纯算子：返回 collection 长度。
- `let` - 作用域算子：在词法局部作用域中求值 body。
- `list` - 纯算子：把参数转换为 Python list。
- `list?` - 纯算子：判断值是否为 list。
- `macro` - 元算子：定义接收未求值 form 并展开的宏。
- `module` - 作用域算子：定义并注册模块。
- `parallel` - Effect 算子：用 asyncio task 并发表达式求值。
- `perform` - Effect 算子：执行 effect。
- `py` - Effect 算子：执行内嵌 async Python，并用 keyword 参数绑定值。
- `python-error` - Effect 定义：py 宿主边界传播的 Python 异常 effect。
- `quote` - 元算子：返回一个表达式，不求值。
- `resume` - Effect 算子：恢复捕获的 effect continuation。
- `set` - 纯算子：把参数转换为 Python set。
- `set?` - 纯算子：判断值是否为 set。
- `spawn` - Effect 算子：创建 asyncio task。
- `tuple` - 纯算子：把参数转换为 Python tuple。
- `tuple?` - 纯算子：判断值是否为 tuple。
- `type` - 纯算子：返回值的类型名称。

## 模块 qy.io

模块：`qy.io`

- `echo` - Effect 算子：print 的别名；打印值并返回最后一个值。
- `print` - Effect 算子：打印求值后的值，并返回最后一个打印值。

## 模块 qy.str

模块：`qy.str`

- `str` - 纯算子：把值转换为文本 symbol。
- `str-concat` - 纯算子：把多个值按文本拼接。
- `str-contains?` - 纯算子：判断文本是否包含子文本。
- `str-empty?` - 纯算子：判断文本是否为空。
- `str-ends-with?` - 纯算子：判断文本是否以给定后缀结束。
- `str-join` - 纯算子：用分隔文本连接值。
- `str-len` - 纯算子：返回文本长度。
- `str-lower` - 纯算子：转换为小写文本。
- `str-replace` - 纯算子：替换文本。
- `str-split` - 纯算子：把文本拆分为 symbol tuple。
- `str-starts-with?` - 纯算子：判断文本是否以给定前缀开始。
- `str-strip` - 纯算子：移除两端空白文本。
- `str-trim` - 纯算子：str-strip 的别名。
- `str-upper` - 纯算子：转换为大写文本。
- `str?` - 纯算子：判断值是否为文本值。
