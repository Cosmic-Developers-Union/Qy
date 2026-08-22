# 错误

用户翻文档最常见的原因就是修错误。如果你把错误变成文档,就能为用户省下大量时间。

## 捕获并改写为人话

如果预期某种错误会发生,捕获它并把信息改写成有用的版本。把它想成一段对话 —— 用户做错了,程序引导他们到对的路上。

差: `EACCES`

好: `无法写入 file.txt。你可能需要运行 'chmod +w file.txt' 来让它可写。`

## 信噪比就是一切

- 越多的无关输出,用户越难发现自己哪里做错了。
- 如果程序会产生多条同类错误,用一条解释性标题把它们归到一起,而不是打印一堆相似的行。

范例:

```
Error: 3 个文件无法读取。
  权限被拒: file1.txt、file2.txt、file3.txt
  提示: 在这些文件上运行 `chmod +r`,或以有读权限的用户运行
```

不要:

```
permission denied: file1.txt
permission denied: file2.txt
permission denied: file3.txt
```

## 眼睛会先看哪里

- 红色首先抓住视线。要克制、有目的地使用。
- 最重要的信息放在输出末尾,让用户先读上下文,再读结论。

```
正在更新 14 个包...
  ✗ foo: 签名不匹配
  ✗ bar: 签名不匹配
  ✗ baz: 签名不匹配
  ... 还有 11 个
运行 `myapp update --force` 重试,或运行 `myapp rollback` 回滚。
```

## 意外或无法解释的错误

当发生了你没想到的事:

- 提供调试与堆栈信息。不要因为觉得是噪音就压制。
- 提供上报 bug 的指引。URL 是好的;预填好的 URL 更好。
- 考虑把调试日志写入文件而不是打到终端,保留用户的屏幕。

```
$ myapp migrate
迁移: 2024_01_users, 2024_02_posts, 2024_03_comments
2024_01_users: ok
2024_02_posts: ok
2024_03_comments: 失败
  意外: IndexError at db/migrate/2024_03_comments.py:42
  完整堆栈已写入 /tmp/myapp-migrate-2024-08-20-1234.log
  请上报 https://github.com/example/myapp/issues/new?body=...
```

## 让 bug 报告变得轻松

一个预填好下列内容的 URL:

- CLI 版本(`--version` 输出)
- 操作系统 / 架构
- 用户运行过的完整命令
- 经过脱敏的日志文件

能把 20 分钟“我复现不出来”的支持对话变成 2 分钟的修复。

## 参见

- `output.md` —— `stdout`/`stderr` 与 TTY 启发式
- `interactivity.md` —— 危险动作的确认
- `arguments-and-flags.md` —— 提示 vs. 必传选项
