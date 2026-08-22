# 子命令

如果一个工具足够复杂,你可以用子命令来降低复杂度。如果有多个紧密相关的工具,把它们合并成一个带子命令的命令,能更易用、更易发现。

## 何时使用子命令

- 工具有超过约 5 个用户可见的不同操作。
- 多个操作共享全局关注点(配置、帮助、版本、认证、存储)。
- 用户在一个 help 入口下就能发现所有操作会有收益。

如果一个工具小而线性,不要为了“看起来像 git”硬塞子命令结构。

## 跨子命令保持一致

- 同样含义用同样的选项名(到处都是 `--json`,而不是这里 `--json` 那里 `--format=json`)。
- 跨子命令的输出格式相似。
- “无参”时的默认行为一致(精简帮助、报错、还是默认动作 —— 选一个,处处一致)。

## 多级子命令使用统一命名

对于有多种对象类型和对应操作的工具,常见模式是二级子命令命名:`名词 动词`。比如 `docker container create`、`docker container ls`、`docker container rm`。

- 选定一个顺序 —— `名词 动词` 或 `动词 名词` —— 然后保持一致。`名词 动词` 更常见。
- 不同对象类型上的动词要保持一致。如果 `create` 在别处用来创建对象,创建 container 时也应该是 `create`。

(延伸阅读: John Starich 的 *User experience, CLIs, and breaking the world*。)

## 不要有歧义或相近的子命令名

`update` vs `upgrade` 会让人困惑。`delete` vs `remove` 会让人困惑。选一个,或加修饰词区分(如 `db upgrade` vs `db update-config`)。

## 应当避免的子命令设计

- “万能兜底”子命令(见 `future-proofing.md`)。
- 任意缩写(见 `future-proofing.md`)。
- 与 shell 内建命令同名的子命令(如 `myapp echo`)—— 让人惊讶。

## 参见

- `help.md` —— 子命令 help 的结构
- `future-proofing.md` —— 兜底子命令与缩写
- `arguments-and-flags.md` —— 跨子命令生效的选项
