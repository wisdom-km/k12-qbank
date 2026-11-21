# practice_item 的一次迁移核对

日期：2026-11-21。解释器是 conda 环境 `k12-qbank` 的 Python 3.12。这不是试用，也不是 AC-01。

空库名是 `k12_d4_schema`。连接串不写进本页。运行器一次方向持有咨询锁 `7724010281418305585`。本机已有的库 `k12` 这次没有迁移，仍停在 V001–V005。

## 命令

空库上 `python scripts/migrate.py` 的三次结果：

| 步骤 | 运行器输出 | 之后的版本表 | practice_item |
| --- | --- | --- | --- |
| up-1 | `up V001 V002 V003 V004 V005 V006` | V001 V002 V003 V004 V005 V006 | 五列。`score` 可空 |
| down | `down V006 V005 V004 V003 V002 V001` | 空。`schema_migrations` 0 行 | `to_regclass` 为空 |
| up-2 | `up V001 V002 V003 V004 V005 V006` | V001 V002 V003 V004 V005 V006 | 与 up-1 相同 |

第二次向前之后，`papers` 14 列，`paper_pages` 10 列，`confirmations` 8 列。约束只有主键 `(paper_id, order_no)` 和外键 `practice_item_paper_id_fkey`，引用 `papers(paper_id)`，没有 `ON DELETE`。没有 `publication`。

## 两类卷

第二次向前之后，用适配器写了一张旧路径单题卷和一张三题卷。单题卷不写 `practice_item`。三题卷的传入顺序是 order 2、3、1，兼容列抄第一条。

| 查询 | 结果 |
| --- | --- |
| `paper-ev-single` 的 `practice_item` 行数 | 0 |
| `paper-ev-single` 的 `papers.question_version_id` | `q-ev-1` |
| `paper-ev-single` 的页 | 1 页，题目版本 `q-ev-1` |
| `paper-ev-multi` 的 `papers.question_version_id` | `q-ev-2`（传入序列的第一条） |
| `paper-ev-multi` 的 `practice_item` | 3 行，按 `order_no` 为 1 `q-ev-4`、2 `q-ev-2`、3 `q-ev-3`。`score` 为空 |
| `paper-ev-multi` 的页 | 3 页，页序跟传入序列：`q-ev-2`、`q-ev-3`、`q-ev-4` |

夹具只用合成标识 `teacher-synth`、`student-synth`。没有姓名，没有整页照片。

## 契约

`python -m unittest tests.practice.test_practice_item_contract -v`。

未设置 `K12_PG_DSN` 时，内存 10 条通过，PostgreSQL 10 条跳过。退出码 0。

把同一套指到空库 `k12_d4_schema` 时，内存 10 条和 PostgreSQL 10 条都通过。退出码 0。其中 e 拆成三条：`test_multi_item_rejects_question_flag_false`、`test_multi_item_rejects_answer_not_approved`、`test_multi_item_rejects_non_applicable_answer`。旧夹具开卷、渲染、复核是 `test_single_item_paper_remains_intact_after_multi_feature_landed`，两边都通过。

多题写入没有新的日志事件。

`K12_ERROR_WEBHOOK_URL` 在这次核对里是空的。没有外部错误接收方。#47 仍打开。
