# ADR 0039 catalog 与 practice 的首个持久适配器

状态：accepted

## 背景

identity 和审计已经在 `K12_PG_DSN` 有值时写入 PostgreSQL。核准、学生卷、页、确认、作答和文件元数据仍只在进程内存里，进程一停就没有了。真实老师需要这些行在重启之后还在。

ADR 0013 的题目规范化表、ADR 0014 的答案版本表、ADR 0015 的知识点表，仍然没有要插入的行。ADR 0015 规定没有行就不建空表。ADR 0028 把第一次真实写入收成 identity 和审计。这三条正文都不改。本条也不是 AC-01。

## 选项

1. 这次把 ADR 0013 到 0015 的空表一起建上。
2. 只建当前会插入的六类行，列按这些对象已经冻结的字段，外加 ADR 0009 的文件元数据。题目规范化表等真有行时再迁移。

## 决定

选 2。practice 仍只通过 `Authorizer` 读授权，不导入 identity。

迁移文件是 `backend/catalog/migrations/V002__catalog_practice.sql`，回滚文件与它同目录。版本号全局唯一，practice 的表放在这一份里，不另写一个 `V002`。一次 up 建齐下面六张表，一次 down 按依赖倒序删掉。CI 对它做 up、down、up。

| 表 | 一行是什么 | 列从哪来 |
| --- | --- | --- |
| approvals | 一条核准快照 | `ApprovalSnapshot` 的字段 |
| papers | 一张已发学生卷 | `Paper` 的字段。发卷时的版本号写死后不随题库更新 |
| paper_pages | 一页卷面 | `PaperPage` 的字段。没有姓名 |
| confirmations | 一条老师确认 | `Confirmation` 的字段 |
| attempts | 一条待确认作答 | `PendingAnswer` 的字段。不是 `login_attempts` |
| files | 一个文件的元数据 | `file_id`、`purpose`、`checksum` |

- 文件字节不进 `files` 表，按 ADR 0009 放在表外。`persist` 为真时字节目录是 `K12_FILE_DIR`。`production` 且该变量为空：一条 ERROR，退出码 1。`development` 且该变量为空：文件仍用内存，并打一条 WARN。进程不读 `FILE_ROOT`。
- 每个用例一个事务。连接失败映射为已有的 `store_failed`。新的业务拒绝码是 `snapshot_not_found`、`paper_not_found`、`slot_conflict`、`file_missing`。
- 适配器是 `backend/catalog/adapters/pg_approvals.py`、`backend/practice/adapters/pg_practice.py` 和 `backend/practice/adapters/pg_files.py`。SQL 只出现在适配器、迁移和运行器里，并且参数化。
- `K12_PG_DSN` 有值时组合根装这三份。内存版只给单测，以及 ADR 0032 的 development 回落。
- 不建 `question_version`、`question_option`、`sub_question`、`question_asset`、`figure_geometry`、`answer_version`、`publication`、`knowledge_point`。那些表仍按 ADR 0013、0014、0015，有行的那次改动再加可回退迁移。

## 后果

重启之后，同一张卷和同一条确认还在。这不表示 AC-01、AC-02 或 AC-04 已经一起走完。知识点检索和多题练习的表这次没有。

## 状态

采纳。2026-11-18。不改 ADR 0012、0013、0014、0015、0021、0028 的正文。C1 按本条写迁移和适配器，不再另写一条落库 ADR。
