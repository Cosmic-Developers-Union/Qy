# 帮助

程序在被询问(或用户卡住)时如何展示自己。

## 默认响应(无参运行,程序需要参数时)

显示精简帮助。应包括:

- 一句话说明程序做什么
- 一两个调用示例
- 选项说明(除非数量很多)
- 提示用户用 `--help` 看完整信息

`jq` 是教科书式范例 —— 用户输入 `jq` 即可看到:

```
$ jq
jq - commandline JSON processor [version 1.6]

Usage:    jq [options] <jq filter> [file...]
    jq [options] --args <jq filter> [strings...]
    jq [options] --jsonargs <jq filter> [JSON_TEXTS...]

jq is a tool for processing JSON inputs, applying the given filter to
its JSON text inputs and producing the filter's results as JSON on
standard output.

The simplest filter is ., which copies jq's input to its output
unmodified (except for formatting, but note that IEEE754 is used
for number representation internally, with all that that implies).

For more advanced filters see the jq(1) manpage ("man jq")
and/or https://stedolan.github.io/jq

Example:

    $ echo '{"foo": 0}' | jq .
    {
        "foo": 0
    }

For a listing of options, use jq --help.
```

如果程序默认就是交互式的(如 `npm init`),可以跳过这条。

## 以下命令都应该显示帮助

```
$ myapp
$ myapp --help
$ myapp -h
```

忽略其它参数 —— 即便在任意位置加 `-h` 也应显示帮助。**不要让 `-h` 有别的含义** —— 用户会出于习惯输入 `-h`,改变它的含义会毁掉整个帮助契约。

类 git 工具还应支持:

```
$ myapp help
$ myapp help subcommand
$ myapp subcommand --help
$ myapp subcommand -h
```

## 帮助文本规则

- 提供反馈/支持入口 —— 在顶层帮助中放上网站或 GitHub 链接。
- 链接到 Web 文档 —— 子命令、深入说明、教程都应可链接。
- 示例优先 —— 用户最先看示例。从简单到复杂,讲一个完整故事。示例太多时,放到 cheat sheet 子命令或 Web 页面。
- 把最常用的选项/子命令放在帮助开头。Git 做得很好:

```
$ git
usage: git [--version] [--help] [-C <path>] [-c <name>=<value>]
           [--exec-path[=<path>]] [--html-path] [--man-path] [--info-path]
           [-p | --paginate | -P | --no-pager] [--no-replace-objects] [--bare]
           [--git-dir=<path>] [--work-tree=<path>] [--namespace=<name>]
           <command> [<args>]

These are common Git commands used in various situations:

start a working area (see also: git help tutorial)
   clone      Clone a repository into a new directory
   init       Create an empty Git repository or reinitialize an existing one

work on the current change (see also: git help everyday)
   add        Add file contents to the index
   mv         Move or rename a file, a directory, or a symlink
   reset      Reset current HEAD to the specified state
   rm         Remove files from the working tree and from the index

examine the history and state (see also: git help revisions)
   bisect     Use binary search to find the commit that introduced a bug
   grep       Print lines matching a pattern
   log        Show commit logs
   show       Show various types of objects
   status     Show the working tree status
…
```

- 使用排版(粗体标题)—— 但在管道场景下要避免暴露转义字符。`heroku apps --help` 是一个清爽的范例,管道分页时不输出转义字符:

```
$ heroku apps --help
list your apps

USAGE
  $ heroku apps

OPTIONS
  -A, --all          include apps in all teams
  -p, --personal     list apps in personal account when a default team is set
  -s, --space=space  filter by space
  -t, --team=team    team to use
  --json             output in json format

EXAMPLES
  $ heroku apps
  === My Apps
  example
  example2

  === Collaborated Apps
  theirapp   other@owner.name

COMMANDS
  apps:create     creates a new app
  apps:destroy    permanently destroy an app
  apps:errors     view app errors
  apps:favorites  list favorited apps
  apps:info       show detailed app information
  apps:join       add yourself to a team app
  apps:leave      remove yourself from a team app
  apps:lock       prevent team members from joining an app
  apps:open       open the app in a web browser
  apps:rename     rename an app
  apps:stacks     show the list of available stacks
  apps:transfer   transfer applications to another user or team
  apps:unlock     unlock an app so any member can join
```

- 拼错时给出建议。`brew update jq` 应提示运行 `brew upgrade jq`。可以询问是否执行建议,但不要擅自执行 —— 无效输入往往意味着逻辑错误,而非手误,替用户做可能改变状态的操作是危险的。Heroku CLI 的做法:

```
$ heroku pss
 ›   Warning: pss is not a heroku command.
Did you mean ps? [y/n]:
```

- 如果 `stdin` 是 TTY 而命令期待管道输入,显示帮助并退出 —— 而不是像 `cat` 那样挂起。或者向 `stderr` 输出一行状态消息。

## 应当避免

- 必须读单独 Web 页面才能理解基础用法的帮助文本。
- 把所有选项按字母顺序平铺、不分组、不分优先级的帮助 —— 读者找不到想要的东西。
- 在管道分页时输出裸 ANSI 转义字符的帮助文本(上面的 `heroku apps --help` 范例避免了这一点)。
- 复用 `-h`(比如在 CSV 模式下让 `-h` 表示“表头行”而不是“帮助”)。
- 为了理想中的帮助格式去改造框架。例如框架默认不生成 Examples 段、命令描述只有英文、子命令只能按字母排序时,不要为了追求本指南的排版去 fork、patch 或硬编码绕过框架。先接受框架默认输出,再在它提供的配置项(长描述、Examples 字段、排序钩子等)内尽量调整;框架做不到的,放到 Web 文档或 man 页面,而不是换掉框架或堆 hacks。

## 参见

- `documentation.md` —— Web/终端/man 文档
- `output.md` —— 帮助文本本身的颜色与动画
- `arguments-and-flags.md` —— `-h`/`--help` 作为选项时的行为
