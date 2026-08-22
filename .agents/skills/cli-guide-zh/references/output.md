# 输出

程序如何与人和其它程序对话。

## 流与 TTY 启发式

- 人优先,机器其次。判断标准是输出目标是否是 TTY。
- **`stdout` 只放机器可读的主体输出;`stderr` 只放日志、状态、错误**。写错流会直接弄脏下游管道。

## 通用接口:基于行的文本

- 默认纯文本,让 `grep`、`awk`、`sort` 等工具能正常工作。
- 一条记录一行是惯例。除非是为了人类友好的视图,否则不要换行、不要把一条逻辑记录拆到多行(真要拆,提供 `--plain` 还原)。

## `--plain` 与 `--json`

- `--plain` —— 当人类友好的排版破坏机器解析时。如果把单元格拆成多行、把表格按屏幕宽度折行、画框线,或用 ANSI 颜色让脚本无法解析,就提供 `--plain` 禁用这一切,恢复一条记录一行。脚本用它;人用默认视图。
- `--json` —— 用于结构化数据。便于与 `jq`、`curl`、Web 服务串联。JSON 是人和机器都想消费时的正确默认。

## 成功输出:简短但不静默

- 完全静默会让人以为卡住。成功时显示*点什么*,但要克制。
- 提供 `-q`/`--quiet` 让需要静默的用户(例如在脚本里)能关掉非关键输出。
- 传统 UNIX 的“成功则静默”默认值在命令是脚本粘合剂时合理;在面向人使用的工具上很少合理。

## 状态变更与状态查看

- 改变状态时,告诉用户发生了什么、新状态是什么。`git push` 是典范:

```
$ git push
Enumerating objects: 18, done.
Counting objects: 100% (18/18), done.
Delta compression using up to 8 threads
Compressing objects: 100% (10/10), done.
Writing objects: 100% (10/10), 2.09 KiB | 2.09 MiB/s, done.
Total 10 (delta 8), reused 0 (delta 0), pack-reused 0
remote: Resolving deltas: 100% (8/8), completed with 8 local objects.
To github.com:replicate/replicate.git
 + 6c22c90...a2a5217 bfirsh/fix-delete -> bfirsh/fix-delete
```

- 让当前状态易于查看。`git status` 是典范:

```
$ git status
On branch bfirsh/fix-delete
Your branch is up to date with 'origin/bfirsh/fix-delete'.

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   cli/pkg/cli/rm.go

no changes added to commit (use "git add" and/or "git commit -a")
```

- 在多步工作流中建议下一条命令。上面 `git status` 的输出中,就建议了用于修改它刚展示的状态的后续命令。

## 显式声明跨边界动作

- 读/写用户没指定的文件(除内部程序状态如缓存之外)。
- 与远程服务器通信,比如下载文件。

这些动作通常需要显式 opt-in,或在被触发时大声告知。

## 用 ASCII 艺术提升信息密度

`ls` 的权限位是经典 —— 一眼就能看出很多信息:

```
-rw-r--r-- 1 root root     68 Aug 22 23:20 resolv.conf
lrwxrwxrwx 1 root root     13 Mar 14 20:24 rmt -> /usr/sbin/rmt
drwxr-xr-x 4 root root   4.0K Jul 20 14:51 security
drwxr-xr-x 2 root root   4.0K Jul 20 14:53 selinux
-rw-r----- 1 root shadow  501 Jul 20 14:44 shadow
-rw-r--r-- 1 root root    116 Jul 20 14:43 shells
drwxr-xr-x 2 root root   4.0K Jul 20 14:57 skel
-rw-r--r-- 1 root root      0 Jul 20 14:43 subgid
-rw-r--r-- 1 root root      0 Jul 20 14:43 subuid
```

初学者会忽略大部分列;熟悉之后,会读出越来越多。

## 颜色

- 有目的地使用。高亮重要的;红色表示错误。别过度 —— 万物皆染色,色彩就失去意义。
- 在以下情况禁用颜色:
  - `stdout`/`stderr` 不是 TTY(分开检查 —— `stdout` 管道给其它程序时,`stderr` 仍可保留颜色)
  - `NO_COLOR` 被设置且非空(与值无关)
  - `TERM=dumb`
  - 传入了 `--no-color`
  - 可选地提供 `<APP>_NO_COLOR` 环境变量

## 动画

- `stdout` 不是 TTY 时不要播放动画。否则 CI 日志里进度条会变成圣诞树。
- 旋转图标、进度条、动画元素只应出现在绑定 TTY 的 `stdout` 上。

## 符号与 emoji

谨慎使用,只为结构或个性。`yubikey-agent` 在不变成文字墙的前提下加上了结构:

```
$ yubikey-agent -setup
🔐 The PIN is up to 8 numbers, letters, or symbols. Not just numbers!
❌ The key will be lost if the PIN and PUK are locked after 3 incorrect tries.

Choose a new PIN/PUK:
Repeat the PIN/PUK:

🧪 Reticulating splines …

✅ Done! This YubiKey is secured and ready to go.
🤏 When the YubiKey blinks, touch it to authorize the login.

🔑 Here's your new shiny SSH public key:
ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBCEJ/
UwlHnUFXgENO3ifPZd8zoSKMxESxxot4tMgvfXjmRp5G3BGrAnonncE7Aj11pn3SSYgEcrrn2sMyLGpVS0=

💭 Remember: everything breaks, have a backup plan for when this YubiKey does.
```

提醒:emoji 过多的输出会显得像玩具。用它们标记章节或关键点,而不是糊墙。

## 默认不应当展示的内容

- 仅供开发者理解的输出 —— 详细模式是 debug 日志的家,不是默认。邀请外部用户/新人评审默认输出,他们能看出你“太近代码反而看不到”的问题。
- 日志级别标签与时间戳打到 `stderr` —— 不要把 `stderr` 当日志文件。除非详细模式,不要 `ERR`/`WARN`/时间戳。

## 分页器

- 长输出使用分页器(如 `less`)。`git diff` 默认就这么做。
- 推荐参数 `less -FIRX`:
  - `-F` —— 一屏能放下就不分页
  - `-I` —— 搜索忽略大小写
  - `-R` —— 启用颜色和 ANSI 转义
  - `-X` —— 退出后保留内容在屏幕
- 仅在 `stdin` 或 `stdout` 是 TTY 时使用分页器。
- 库(例如 Python 的 `pypager`)通常比直接管道到 `less` 更稳健。

## 参见

- `errors.md` —— 错误输出与信噪比
- `help.md` —— 帮助文本格式
- `arguments-and-flags.md` —— `--plain`/`--json`/`--quiet` 作为选项
- `environment-variables.md` —— `NO_COLOR` 等相关环境变量
