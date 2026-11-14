# 门禁改法

检查失败时按编号改。不要为了变绿去改 `scripts/check*`、CI 或本文件，除非用户明确要求改规则。

| 编号 | 常见问题 | 改法 | 规格 |
| --- | --- | --- | --- |
| M-01 | 不是 git 仓库，或没有提交 | 在本仓库提交一小步。长期还要把 GitHub 的 main 设为只经 PR 合入 | AGENTS 强制项 |
| M-02 | README 里找不到启动命令 | 命令必须和 `scripts/check.conf` 的 `RUN_CMD` 一致。`RECORD` 只表示这句话写上了。教学服务存在之后再填 `SERVICE_CMD`，检查才会执行它 | README |
| M-03 | `.env` 被跟踪，或像密钥的字符串在仓库里 | 从仓库移除，写入本机 `.env`，轮换已经暴露的密钥。提交 `.env.example`，不要提交值 | R-1，RULES |
| M-04 | core 里有 `print`，或 import 了 logging | 改用注入的 `Logger` 和 `LogEvent`。请求 ID 从入口传下来 | ADR 0008，ARCHITECTURE 运行日志 |
| M-05 | 空的 catch 或 `except: pass` | 记录一次带 request_id 的错误，并向外返回 Err 或给人话提示 | RULES L-02 |
| M-06 | 测试命令失败或没填 | 补测试。修 bug 时先有一条失败的回归测试。`DOCS` 只表示文档冒烟，不是 core 单测、契约或端到端。业务冒烟用 `BUSINESS_TEST_CMD` | ARCHITECTURE 测试策略 |
| M-08 | CI 没有跑 `scripts/check` | 保留 `.github/workflows/ci.yml` 里的 check 任务，不要加会跳过它的条件 | RULES |
| M-09 | 有依赖清单却没有锁文件 | 生成锁文件并提交。安装命令用锁定安装 | ADR 0010 选定技术栈之后 |
| LINT | 跨切片导入了内部模块，或出现 utils | 改为导入对方的 `api`。删掉 utils / helpers / common | ADR 0003、0004 |
| F-02 | domain 或 application 导入了框架、ORM 或模型 SDK | 把该 import 移到 adapters 或组合根 | ARCHITECTURE 依赖允许表 |
| F-03 | 导入了其他切片的 domain、application 或 adapters，包括等价的相对导入 | 只导入 `backend/<切片>/api.py`。相对导入会先按源文件所在的包解析 | ARCHITECTURE 禁止 F-03 |
| F-04 | 出现 utils、helpers 或 common 目录 | 删掉该目录，把代码放回它所属的切片 | ARCHITECTURE 禁止 F-04 |
| F-10 | 单个 Python 文件超过 800 行 | 按隐藏的决定拆开。要保留必须有豁免和 ADR | ARCHITECTURE 文件大小 |
| F-11 | 组合根导入了 domain | 组合根只装配 application 和 adapters | ARCHITECTURE 禁止 F-11 |
| F-13 | 出现当前阶段以外的切片、安卓工程、桌面壳或 Electron | 删掉该目录或依赖。若规格已经改到下一段，先改执行计划和 ARCHITECTURE，再在同一次改动里改 `scripts/check.conf` 的 `PHASE_SLICES`。空白值仍是 catalog 和 practice。非空环境变量 `PHASE_SLICES` 会覆盖文件，本地变绿前先确认没有设错 | `docs/exec-plans/active/rational-number-loop.md`，ADR 0011 |
| F-14 | `apps/` 里导入了 backend | 改成调用 HTTPS API，不要引用服务端源码 | ARCHITECTURE 依赖允许表 |
| L-03 | core 里有 print，或 import 了 logging、structlog、loguru | 改用注入的 Logger 和 LogEvent | ARCHITECTURE 运行日志 |
| L-05 | log 调用带了密钥、姓名、学号，或用 f-string 拼日志 | 删掉该字段，改成固定字段的 LogEvent | ARCHITECTURE 绝不记 |
