# 信号与控制字符

中断契约。

## Ctrl-C(SIGINT)→ 尽快退出

- 立即说点什么,再开始清理。用户想知道自己被听见了。
- 给清理代码加超时,让它不可能永远挂起。按两次 Ctrl-C 的用户应该能强制退出。

```
^C
正在关闭(再按 Ctrl-C 强制退出)...
```

## 清理阶段 Ctrl-C → 跳过清理

如果清理可能耗时较长,告诉用户再按一次会发生什么 —— 特别是当它是破坏性的时候。Docker Compose 是清晰的范例:

```
$  docker-compose up
…
^CGracefully stopping... (press Ctrl+C again to force)
```

## 程序要能接受“未清理”的状态

程序启动时应该能接受上次的清理没有跑完的情况。这与 crash-only 原则(`robustness.md`)配对:立即退出、把清理延后到下次运行、下次运行修复任何部分状态。

## 其它值得了解的信号

- SIGTERM —— 礼貌的“请退出”信号。默认行为应与 SIGINT 相同:清理后退出,带超时。
- SIGHUP —— 历史上“终端挂断”。很多守护进程在 SIGHUP 时重载配置。对前台 CLI,SIGHUP 通常意味着控制终端消失了;按 SIGTERM 处理。
- SIGPIPE —— 程序试图写一个没有读取端的管道(比如用户管道到 `head`,`head` 退出了)。默认行为是直接死 —— 没问题。只是别让它在程序有机会 flush 或清理部分输出之前就把程序杀掉。

## 参见

- `interactivity.md` —— 更广义的“让用户能退出”原则
- `robustness.md` —— crash-only 原则
