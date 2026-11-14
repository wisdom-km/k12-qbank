# 参与修改

先读 [AGENTS.md](AGENTS.md) 的强制项，再读 [RULES.md](RULES.md)。冲突时以这两份为准。

常用命令：

| 做什么 | 命令 |
| --- | --- |
| 查看骨架状态 | `python scripts/status.py` |
| 文档冒烟 | `python scripts/smoke_docs.py` |
| 最小 core 测试 | `python -m unittest discover -s tests -v` |
| Windows 全量检查 | `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` |
| 干净环境全量检查 | `bash scripts/check` |

`main` 只经 pull request 合入。不要提交 `.env`。第一段不要新建 `catalog` 和 `practice` 以外的切片，不要建安卓工程或桌面壳。

业务拒绝返回 `Ok` 或 `Err`，不要用异常表示拒绝。日志走注入的 `Logger`，不要在领域和用例里 `print`。
