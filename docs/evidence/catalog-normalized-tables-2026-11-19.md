# 规范化题目表和答案表的一次迁移核对

日期：2026-11-19。解释器是 conda 环境 `k12-qbank` 的 Python 3.12.16。这不是试用，也不是 AC-01。

空库名是 `k12_d1_schema`。连接串不写进本页。运行器一次方向持有咨询锁 `7724010281418305585`。本机已有的库 `k12` 只执行了向前，应用了 `V004`，没有回滚。

## 命令

空库上 `python scripts/migrate.py` 的三次结果：

| 步骤 | 已应用版本 | 之后的版本表 | 业务表 |
| --- | --- | --- | --- |
| up-1 | V001 V002 V003 V004 | V001 V002 V003 V004 | 含 `questions` 和 `answers` |
| down | V004 V003 V002 V001 | 空 | 没有。只剩 `schema_migrations` |
| up-2 | V001 V002 V003 V004 | V001 V002 V003 V004 | 含 `questions` 和 `answers` |

契约测试 `python -m unittest tests.test_catalog_practice_contract` 在内存上通过。同一套在这个空库上通过，退出码 0。未核准的快照不写 `questions`。两边都核准时写入一行。再次核准同一个 `question_id` 时，题库快照的题干会变，`questions` 里第一次的题干还在。

核准快照没有题型。这一行的 `type` 是 `unresolved`，题干是一个 text 片段，答案的 `origin` 是 `teacher`。

`K12_ERROR_WEBHOOK_URL` 在这次核对里是空的。没有外部错误接收方。#47 仍打开。
