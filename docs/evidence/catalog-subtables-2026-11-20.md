# 题目和答案子表的一次迁移核对

日期：2026-11-20。解释器是 conda 环境 `k12-qbank` 的 Python 3.12.16。这不是试用，也不是 AC-01。

空库名是 `k12_d2_schema`。连接串不写进本页。运行器一次方向持有咨询锁 `7724010281418305585`。本机已有的库 `k12` 只执行了向前，应用了 `V005`，没有回滚。

## 命令

空库上 `python scripts/migrate.py` 的三次结果：

| 步骤 | 已应用版本 | 之后的版本表 | 业务表 |
| --- | --- | --- | --- |
| up-1 | V001 V002 V003 V004 V005 | V001 V002 V003 V004 V005 | 含五张子表 |
| down | V005 V004 V003 V002 V001 | 空 | 没有。只剩 `schema_migrations` |
| up-2 | V001 V002 V003 V004 V005 | V001 V002 V003 V004 V005 | 含五张子表 |

五张子表是 `question_option`、`sub_question`、`question_asset`、`answer_part`、`answer_asset`。`figure_geometry` 和 `answer_decision` 没有建。`questions` 和 `answers` 的列没有改。`approvals` 增加可空的 `type` 和 `structure`，用来放下核准快照上的题型。

第二次向前之后，用适配器写入一份选择题、一份带两个小问的综合题、一条带两个 part 的答案，以及一条题型为 `solution` 的核准。SELECT 结果：

| 查询 | 结果 |
| --- | --- |
| 选择题的选项 | 2 |
| 选择题的 crop | 1 |
| 综合题的小问 | 2 |
| 综合题第一个小问的选项 | 2 |
| 答案的 part | 2 |
| 答案的 crop | 1 |
| 核准行的 type | solution |
| 核准行的选项 | 0 |
| 核准行的答案 | 1 |
| type 为 unresolved 的题目行 | 0 |

没有题型的核准快照不写 `questions`。已有的 `question_id` 再核准时不改那一行。

## 回填

本机库 `k12` 上只跑了 `python scripts/backfill_question_type.py --dry-run`。退出码 0。没有执行 `--apply`。

```text
scanned 0
eligible 0
skipped_missing 0
skipped_shape 0
would_update 0
updated 0
```

这台库里没有 `type = unresolved` 的题目行，所以没有要刷的行。

`K12_ERROR_WEBHOOK_URL` 在这次核对里是空的。没有外部错误接收方。#47 仍打开。
