# 交互

提示、密码与退出路径。

## 只在 `stdin` 是 TTY 时才提示

这是判断数据是被管道送入还是在脚本里运行的相当可靠方式。如果 `stdin` 不是 TTY,提示就不工作 —— 报错告诉用户应该传哪个选项。

## 遵守 `--no-input`

给用户(和 CI)一个显式的逃逸口来禁用所有提示。如果命令需要输入且设置了 `--no-input`,报错并告诉用户如何用选项传入。

```
$ myapp deploy --no-input
Error: 必传参数 'environment' 未提供。
请通过选项传入: myapp deploy --environment=prod
```

## 输入密码时不要回显

关闭终端回显。每种语言都有对应的辅助方法。(Python: `getpass.getpass()`。Go: `golang.org/x/term`。Node: 内置 TTY API。)

## 始终让用户能退出

让 Ctrl-C 可用。别学 `vim`(把用户困在一个难以退出的模式里)。

- 大多数程序:Ctrl-C 立即退出,不再追问。
- 包装器(SSH、tmux、telnet)接管了终端,Ctrl-C 无法退出这些程序,所以要清晰暴露转义序列。SSH 的 `~` 转义字符是典范:`~.` 断开,`~^Z` 后台,等等。

## 参见

- `signals.md` —— Ctrl-C 处理契约
- `arguments-and-flags.md` —— `--no-input` 作为选项
