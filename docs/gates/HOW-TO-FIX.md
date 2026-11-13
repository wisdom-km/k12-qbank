# 门禁改法

检查失败时按编号改。不要为了变绿去改 `scripts/check*`、CI 或本文件，除非用户明确要求改规则。

| 编号 | 常见问题 | 改法 | 规格 |
| --- | --- | --- | --- |
| M-01 | 不是 git 仓库，或没有提交 | 在本仓库提交一小步。长期还要把 GitHub 的 main 设为只经 PR 合入 | AGENTS 强制项 |
| M-02 | README 里找不到启动命令 | 命令必须和 `scripts/check.conf` 的 `RUN_CMD` 一致，并且在新终端能跑 | README |
| M-03 | `.env` 被跟踪，或像密钥的字符串在仓库里 | 从仓库移除，写入本机 `.env`，轮换已经暴露的密钥。提交 `.env.example`，不要提交值 | R-1，RULES |
| M-04 | core 里有 `print`，或 import 了 logging | 改用注入的 `Logger` 和 `LogEvent`。请求 ID 从入口传下来 | ADR 0008，ARCHITECTURE 运行日志 |
| M-05 | 空的 catch 或 `except: pass` | 记录一次带 request_id 的错误，并向外返回 Err 或给人话提示 | RULES L-02 |
| M-06 | 测试命令失败或没填 | 补测试。修 bug 时先有一条失败的回归测试 | ARCHITECTURE 测试策略 |
| M-08 | CI 没有跑 `scripts/check` | 保留 `.github/workflows/ci.yml` 里的 check 任务，不要加会跳过它的条件 | RULES |
| M-09 | 有依赖清单却没有锁文件 | 生成锁文件并提交。安装命令用锁定安装 | ADR 0010 选定技术栈之后 |
| LINT | 跨切片导入了内部模块，或出现 utils | 改为导入对方的 `api`。删掉 utils / helpers / common | ADR 0003、0004 |
