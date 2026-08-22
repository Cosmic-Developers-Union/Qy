# 环境变量

环境变量用于随命令运行上下文变化的行为 —— 终端会话、项目、机器。

## 命名

- 仅 `A-Z`、`0-9`、`_`;不能以数字开头。
- `O_O` 和 `OWO` 是唯一合法的表情。
- 不要抢占广泛使用的名字 —— 参考 POSIX 标准环境变量。

## 单行值

单行值优先。多行值会让 `env` 命令和大多数工具很难用。

## 检查的标准环境变量

| 变量                                                                              | 用途                                       |
|-----------------------------------------------------------------------------------|----------------------------------------|
| `NO_COLOR` / `FORCE_COLOR`                                                        | 禁用 / 强制颜色                              |
| `DEBUG`                                                                          | 详细输出                                  |
| `EDITOR`                                                                         | 提示用户编辑文件或多行输入                    |
| `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` / `NO_PROXY`                           | 网络操作(HTTP 库通常已自动检查)               |
| `SHELL`                                                                          | 交互式打开用户偏好的 shell(脚本里用 `/bin/sh`)    |
| `TERM` / `TERMINFO` / `TERMCAP`                                                  | 终端相关的转义序列                            |
| `TMPDIR`                                                                         | 临时文件                                  |
| `HOME`                                                                           | 定位配置文件                                |
| `PAGER`                                                                          | 输出分页器                                  |
| `LINES` / `COLUMNS`                                                              | 屏幕尺寸相关的输出                            |
| `XDG_CONFIG_HOME` / `XDG_DATA_HOME` / `XDG_CACHE_HOME` / `XDG_RUNTIME_DIR`       | XDG Base Directory 规范                     |

## 从 `.env` 读项目级上下文

如果命令定义的某些环境变量在用户处于特定目录时不太可能改变,也应该从本地 `.env` 文件读取。让用户能为不同项目配置不同行为,不必每次都显式指定。多数语言都有 `.env` 库(Rust、Node、Ruby、Python)。

## 不要用 `.env` 替代真正的配置文件

`.env` 有真实的局限:

- 通常不进版本控制(无历史)。
- 单一数据类型:字符串。
- 容易乱。
- 容易踩编码坑。
- 经常塞着本该更安全存放的凭据。

如果这些局限会影响可用性或安全性,就用专门的配置文件。

## 不要从环境变量读密钥

诱惑很大,但它们会泄漏:

- 导出的环境变量会传给每个子进程,继而进入日志或更远。
- `curl -H "Authorization: Bearer $BEARER_TOKEN"` 这种 shell 替换会泄漏到全局可读的进程状态。(cURL 提供 `-H @filename` 作为敏感 header 的替代。)
- `docker inspect` 会向任何有 Docker daemon 访问权限的人暴露容器环境变量。
- `systemctl show` 会向系统上任何人暴露 systemd 单元的环境变量。

密钥应只通过凭据文件、管道、`AF_UNIX` socket、密钥管理服务或其它 IPC 机制传入。

## 参见

- `configuration.md` —— 环境变量在整体配置优先级中的位置
- `arguments-and-flags.md` —— 与选项平行的规则
- `output.md` —— `NO_COLOR` / `FORCE_COLOR` / `TERM` / `PAGER`
