# 命名

程序的名字在 CLI 上格外重要 —— 用户每天要打很多次,需要好记、好打。

## 经验法则

- 简单、易记的单词。别太通用,否则你会撞其它命令的脚、让用户困惑。(ImageMagick 和 Windows 都用过 `convert`。)
- 只小写,需要时用短横线。`curl` 是好名字;`DownloadURL` 不是。
- 短。用户每天要打很多次。*也别太短* —— 最短的名字留给最常用的工具(`cd`、`ls`、`ps`)。
- 好打。如果用户一整天都要敲,对手指友好。避免别扭的单手交替。

## 真实案例

Docker Compose 在变成 `docker compose` 之前,叫 `plum`。这个名字单手打起来别扭得像跳房子,很快改名 `fig` —— 更短,节奏也更顺。

## UNIX 传统

> “请注意对缩写和避免大写字母的执着;[Unix] 是被重复性压力损伤视为黑肺病的矿工式人物发明的系统。长名字会被磨成三个字母的小桩,像被河水磨圆的石头。” —— Neal Stephenson,《In the Beginning was the Command Line》

UNIX 的传统是短、小写、经常缩写。别反抗;顺着它。

## 子命令与选项命名

也应遵循同一套原则:短、小写、合惯例。参见 `subcommands.md` 与 `arguments-and-flags.md`。

## 参见

- `subcommands.md` —— 工具内命名
- `arguments-and-flags.md` —— 选项命名约定
