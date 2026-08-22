# 配置

三类配置,对应三种机制。合适的机制取决于特异性、稳定性和复杂度。

## 分类

| 类别                       | 示例                       | 机制                              |
|----------------------------|--------------------------|---------------------------------|
| 每次调用可能不同           | debug 级别、dry-run        | 选项(可选环境变量)                    |
| 用户稳定,项目/机器间不同   | 非默认路径、颜色、代理      | 选项 + 环境变量(XDG 配置)              |
| 项目内稳定,所有用户一致   | 构建配置                  | 版本化的、命令专属的文件                |

### 每次调用 → 选项

- Debug 输出级别
- Dry-run 模式
- 输出格式覆盖(`--json`、`--plain`)

这些往往在调用瞬间设置。选项是正解。环境变量可选。

### 用户级、项目级 → 选项 + 环境变量

- 程序启动所需的非默认路径
- 颜色是否开启
- HTTP 代理

这类配置往往针对单台电脑,但项目间可能不同。用户想在 shell profile 里设环境变量(全局生效),或在 `.env` 里设(项目内生效)。如果配置足够复杂,可以有独立配置文件;但环境变量通常够用。

### 项目级、所有用户 → 版本化的文件

- `Makefile`
- `package.json`
- `docker-compose.yml`
- `myapp.config.yaml`

这类配置应该进版本控制。

## XDG Base Directory 规范

2010 年 X Desktop Group(现 freedesktop.org)制定了配置文件基准目录的规范。目标之一是限制用户家目录下 dotfile 的蔓延,改用通用的 `~/.config` 目录。已被 `yarn`、`fish`、`wireshark`、`emacs`、`neovim`、`tmux` 等众多项目支持。

相关变量:

- `XDG_CONFIG_HOME` —— 用户配置基目录(默认 `~/.config`)
- `XDG_DATA_HOME` —— 用户数据文件基目录(默认 `~/.local/share`)
- `XDG_CACHE_HOME` —— 用户缓存基目录(默认 `~/.cache`)
- `XDG_RUNTIME_DIR` —— 用户运行时文件(socket、PID 文件等)

尊重这些变量。能写 `~/.config/myapp` 就别直接写 `~/.myapp`。

(完整规范:[specifications.freedesktop.org/basedir-spec](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)。)

## 修改不属于自己的配置前要征求同意

- 优先新建配置文件(如 `/etc/cron.d/myapp`),不要追加到已有文件(如 `/etc/crontab`)。
- 如果必须追加系统级配置,用日期注释区分你的改动:

```
# 2024-08-20 myapp: 由 myapp install 添加
*/15 * * * * myuser /usr/local/bin/myapp tick
```

## 优先级

配置参数按以下顺序生效(高 → 低):

1. 选项
2. shell 环境变量
3. 项目级配置(如 `.env`)
4. 用户级配置
5. 系统级配置

## 参见

- `environment-variables.md` —— 配置中环境变量那一面
- `arguments-and-flags.md` —— 配置中选项那一面
