# publication 的一次迁移核对

日期：2026-11-21。解释器是 conda 环境 `k12-qbank` 的 Python 3.12。这不是试用，也不是 AC-01。

空库名是 `k12_d5_schema`。连接串不写进本页。运行器一次方向持有咨询锁 `7724010281418305585`。本机库 `k12` 只向前：从 V001–V005 到 V001–V007。当时双方核准且未 retired 的 approval 是 0，active publication 也是 0。没有回滚。

## 第二次空库 up / down / up

端口和出卷闸落地之后重跑。三次运行器输出：

| 步骤 | 运行器输出 | 之后 |
| --- | --- | --- |
| down | `down V007 V006 V005 V004 V003 V002 V001` | `schema_migrations` 0 行。`to_regclass('public.publication')` 为空 |
| up-1 | `up V001 V002 V003 V004 V005 V006 V007` | 版本表 V001–V007。双方核准且未 retired 为 0。`status='active'` 为 0 |
| down | `down V007 V006 V005 V004 V003 V002 V001` | 再次为空 |
| up-2 | `up V001 V002 V003 V004 V005 V006 V007` | 与 up-1 相同。两边计数仍是 0 |

退出码都是 0。

## 四行样本

up-2 之后撤掉 V007，重新插入 4 行合成 approval，再 `up V007`。退出码 0。

```text
 both_approved_not_retired
---------------------------
                         2

 active_publication
--------------------
                  2

  publication_id   | question_version_id | answer_version_id | layout_template_id | subject_id | status
-------------------+---------------------+-------------------+--------------------+------------+--------
 pub-q-d5-1-a-d5-1 | q-d5-1              | a-d5-1            |                    | math       | active
 pub-q-d5-4-a-d5-4 | q-d5-4              | a-d5-4            |                    | science    | active

 q_d5_2_in_publication
-----------------------
                     0
```

`q-d5-1` 双方核准且未 retired，学科 math。`q-d5-4` 同样，学科 science。`q-d5-2` 双方核准但 retired，不在表里。`q-d5-3` 答案未核准，不在表里。`layout_template_id` 为空。

## 没有发布时的拒绝

`compose_multi_item_paper` 自己不写日志。契约测试 `test_multi_item_rejects_item_without_active_publication` 得到 `Err`，码是 `no_active_publication`，paper、page、practice_item 都没有留下。

单题 `issue_paper` 在传入空账本时走既有的 `use_case_refused`。同一次测试里的事件结果是 `no_active_publication`。没有新的事件名。

旧卷测试 `test_old_paper_opens_even_when_publication_missing` 在没有 publication 行时仍开卷、渲染、复核通过。开卷函数没有改。

## 契约

`python -m unittest tests.catalog.test_publications_contract tests.practice.test_practice_item_contract -v`。

未设置 `K12_PG_DSN` 时，内存通过，PostgreSQL 跳过。退出码 0。

把同一套指到空库 `k12_d5_schema` 时，内存和 PostgreSQL 一起跑，37 条通过，退出码 0。其中 a2、唯一约束和未知 status 只在 PostgreSQL 上执行。

夹具只用合成标识。没有姓名，没有整页照片。

`K12_ERROR_WEBHOOK_URL` 在这次核对里是空的。没有外部错误接收方。#47 仍打开。
