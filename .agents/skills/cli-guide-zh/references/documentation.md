# 文档

帮助文本解决“这个选项现在能干嘛”;文档解决“我到底该怎么用这个工具”。两者都要提供。

## 三个渠道,三种受众

| 渠道            | 优势                                       | 注意点                            |
|---------------|------------------------------------------|---------------------------------|
| Web 文档   | 可搜索、可链接、格式丰富、最包容              | 容易和代码漂移;不能离线                |
| 终端文档   | 快速、与安装版本同步、可离线                 | 不易分享链接、格式受限                |
| man 手册   | 本能反应(`man mycmd`)、适合做参考           | 不是人人知道;不在所有平台            |

## Web 文档

- 可被搜索。
- 各页面/段落都可被独立链接,让用户能直接分享“具体某个行为”的 URL。
- Web 是最包容的文档格式 —— 如果只能选一个,先做这个。

## 终端文档

- 内置 `--help` 与 `help` 子命令覆盖基础。
- `--cheatsheet` 或 `examples` 子命令覆盖长尾 recipe。
- 对于长结构化参考,考虑提供 `myapp docs` 子命令,在用户的分页器中打开本地文档树。

## man 手册

- 很多用户会本能地试 `man mycmd`。
- 用 `ronn` 等工具从单一源同时生成 Web 文档与 man 页面。
- 不要单独依赖 `man` —— 不是人人知道,且不是所有平台都有。
- 也通过 `help` 子命令暴露 man 页面(如 `npm help ls`):

```
NPM-LS(1)                                                            NPM-LS(1)

NAME
       npm-ls - List installed packages

SYNOPSIS
         npm ls [[<@scope>/]<pkg> ...]

         aliases: list, la, ll

DESCRIPTION
       This command will print to stdout all the versions of packages that are
       installed, as well as their dependencies, in a tree-structure.
…
```

## 教程 vs 参考

- 参考 住在 `--help` 与 man 手册中。每个选项、每个行为,无叙事。
- 教程 应在 Web 上,或在 `myapp tutorial` 子命令里。端到端走完一个真实工作流。
- 示例 应放在 `--help` 顶部(以及长尾)放在 Web 或 cheat sheet 中。Recipe,不是叙事。

## 参见

- `help.md` —— 帮助文本本身
- `output.md` —— 终端上文档/帮助的格式
