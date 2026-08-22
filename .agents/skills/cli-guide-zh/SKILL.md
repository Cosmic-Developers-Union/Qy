---
name: cli-guide-zh
description: 在设计、评审或重构命令行程序时使用。本文件是索引,先读哲学与反模式清单;再按需打开 references/<domain>.md 读具体领域(帮助、输出、错误、参数、信号等)。
---

# CLI 设计指南

[clig.dev](https://clig.dev/)（Command Line Interface Guidelines）的中文工作参考,作者 Aanand Prasad、Ben Firshman、Carl Tashian、Eva Parish。本文件是索引 —— 先读这里的哲学和反模式清单,再按需进入 references/ 读取对应领域。

何时使用: 正在设计、评审或重构 CLI 程序;在“这里应该长什么样”的争论中需要依据;在上线前检查默认行为。

## 哲学(必读)

终端是以人为本的文本界面,不再是套在脚本平台上的 REPL。下列九条原则是 references/ 中每条规则背后的视角:

1. 以人为本的设计 —— 优先为人服务,其次才考虑脚本。UNIX 遗风（精简、静默、面向机器）不再是默认。
2. 能组合的简单部件 —— 可组合性是底线。尊重 `stdin`/`stdout`/`stderr`、退出码、信号与基于行的文本。结构化数据可使用 JSON。
3. 跨程序的一致性 —— 沿用既有约定,让用户可以靠直觉和肌肉记忆操作。除非有意,不要打破惯例。
4. 说得恰到好处 —— 输出太少让人以为卡住了;太多又会淹没关键信号。目标清晰、克制。
5. 易于发现 —— CLI 不必是“只能死记硬背”。充分的帮助、示例、建议和错误指引让它可学。
6. 对话是常态 —— 用户通过试错迭代;把输出视为对话,不是一次性报告。
7. 健壮性 —— 既是客观的（处理坏输入、尽可能幂等）,也是主观的（感觉可靠、响应迅速、不脆弱）。
8. 同理心 —— 软件应让用户感觉作者站在自己这边。
9. 混沌 —— 终端世界本就混乱;规则是用来被打破的,但要目的明确。

> “当某个标准被证明会损害生产力或用户体验时,就抛弃它。” —— Jef Raskin,《The Humane Interface》

> “假设任何程序的输出都会成为另一个未知程序的输入。” —— Doug McIlroy

## 基础(始终适用)

四条规则适用于所有 CLI。不可妥协。

- 用参数解析库的能力,不要为理想输出改造框架。你是框架的使用者;框架默认生成的帮助、补全、描述如果达不到理想状态,先接受它,再在框架允许的配置范围内调整,而不是 fork、monkey-patch 或硬编码绕过框架,去换取某个花哨的输出。刻意改造框架会扩大依赖面和维护范围,得不偿失。
- 使用参数解析库 —— 语言自带或知名第三方,不要手写。常见选择:Python `argparse`/`click`/`typer`,Go `cobra`/`cli`,Rust `clap`,Node `oclif`/`parseArgs`,Java `picocli`,Haskell `optparse-applicative`,跨平台 `docopt`。
- **退出码 0 表示成功、非零表示失败**,并把非零码映射到有意义的失败模式。写错退出码会破坏所有依赖它的脚本和管道。
- `stdout` 承载主体输出、机器可读内容,`stderr` 承载日志、状态、错误。**两者混写会直接弄脏下游管道**。
- `-h` 和 `--help` 都生效,即使带其它参数也如此。

## references/(按需读取)

按你正在处理的领域打开对应文件:

| 主题     | 文件 |
|--------|------|
| 帮助文本(默认响应、`-h`/`--help`、示例、拼写建议) | `references/help.md` |
| Web、终端、man 文档 | `references/documentation.md` |
| 输出(`stdout`/`stderr`、TTY、`--plain`、`--json`、颜色、分页、动画、emoji) | `references/output.md` |
| 错误信息(改写、信噪比、调试信息、bug 报告) | `references/errors.md` |
| 参数 vs 选项、标准选项名、危险等级、密钥、`-` | `references/arguments-and-flags.md` |
| 提示、TTY 检查、`--no-input`、密码不回显、退出 | `references/interactivity.md` |
| 子命令命名与一致性 | `references/subcommands.md` |
| 校验、响应性、进度、并行、恢复、crash-only | `references/robustness.md` |
| 叠加式变更、弃用、兜底子命令、缩写、定时炸弹 | `references/future-proofing.md` |
| Ctrl-C / 清理 / 强制停止 | `references/signals.md` |
| XDG 配置、项目/用户/系统、优先级 | `references/configuration.md` |
| 环境变量命名、标准变量、`.env`、密钥 | `references/environment-variables.md` |
| 命令名命名 | `references/naming.md` |
| 单二进制、原生包、卸载 | `references/distribution.md` |
| 遥测:opt-in、opt-out、替代方案 | `references/analytics.md` |

## 反模式清单

评审 CLI 时逐项核对,每条对应到上面的某个领域文件。

- [ ] 使用参数解析库(没有手写解析)
- [ ] 成功返回 `0`,失败返回非零(并映射到失败模式)
- [ ] 主体输出 → `stdout`,日志/错误 → `stderr`
- [ ] `-h` 和 `--help` 都生效,即使带其它参数 —— 参见 `references/help.md`
- [ ] 默认无参运行显示精简帮助 —— 参见 `references/help.md`
- [ ] 帮助以示例开头 —— 参见 `references/help.md`
- [ ] 拼错命令后给出建议;状态变更后提示下一步 —— 参见 `references/help.md`、`references/output.md`
- [ ] 默认人读输出;提供 `--json` 供机器;提供 `--plain` 防止人类排版破坏解析 —— 参见 `references/output.md`
- [ ] 遵守 `NO_COLOR`、`TERM=dumb`、非 TTY、`--no-color` —— 参见 `references/output.md`
- [ ] 非 TTY 的 `stdout` 不播放动画 —— 参见 `references/output.md`
- [ ] 错误改写为人话,带可操作的建议 —— 参见 `references/errors.md`
- [ ] 优先选项而非参数;提供完整选项名 —— 参见 `references/arguments-and-flags.md`
- [ ] 使用标准选项名(`-h`、`-v`、`--json`、`--dry-run` 等) —— 参见 `references/arguments-and-flags.md`
- [ ] 默认值照顾大多数用户 —— 参见 `references/arguments-and-flags.md`
- [ ] `stdin` 非 TTY 时跳过提示;遵守 `--no-input` —— 参见 `references/interactivity.md`
- [ ] 危险操作有确认;提供 `--dry-run`;重度操作支持 `--confirm="name"` —— 参见 `references/arguments-and-flags.md`
- [ ] 文件型输入/输出支持 `-` —— 参见 `references/arguments-and-flags.md`
- [ ] 密钥绝不从选项或环境变量读取 —— 参见 `references/arguments-and-flags.md`、`references/environment-variables.md`
- [ ] Ctrl-C 快速退出;清理阶段第二次 Ctrl-C 跳过清理 —— 参见 `references/signals.md`
- [ ] 配置优先级:选项 > 环境变量 > 项目 > 用户 > 系统 —— 参见 `references/configuration.md`
- [ ] 读取通用环境变量(`NO_COLOR`、`HTTP_PROXY`、`EDITOR` 等) —— 参见 `references/environment-variables.md`
- [ ] 命令名短、小写、易输入 —— 参见 `references/naming.md`
- [ ] 单二进制或平台包管理器分发 —— 参见 `references/distribution.md`
- [ ] 卸载说明易找 —— 参见 `references/distribution.md`
- [ ] 无同意不采集遥测 —— 参见 `references/analytics.md`

## 引用与延伸阅读

- [clig.dev](https://clig.dev/) —— Aanand Prasad、Ben Firshman、Carl Tashian、Eva Parish
- 《The Humane Interface》—— Jef Raskin(标准引文出处)
- 《In the Beginning was the Command Line》—— Neal Stephenson(命名篇)
- *Crash-only software: More than meets the eye* —— crash-only 原则
- 《The Design of Everyday Things》—— Don Norman
- *The Anti-Mac User Interface* —— Don Gentner、Jakob Nielsen
- *The Poetics of CLI Command Names* —— 命名
- *12 Factor CLI Apps* —— Jeff Dickey(flags-over-args、机器可读输出)
- *GNU Coding Standards* —— 长选项约定
- *User experience, CLIs, and breaking the world* —— John Starich(子命令顺序)
- *Do What I Mean* —— DWIM 讨论
- 《The Unix Programming Environment》—— Kernighan & Pike
- *POSIX Utility Conventions*
- 1987 年原版 Macintosh Human Interface Guidelines
- no-color.org —— `NO_COLOR` 标准
- Google 《Writing Helpful Error Messages》、Nielsen Norman Group 《Error-Message Guidelines》
- *Open Source Metrics* —— 遥测替代方案
