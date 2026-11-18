# ADR 0029 迁移

状态：accepted

## 背景

第一次写入 PostgreSQL 要带可回退的迁移。迁移文件要能在临时数据库里向前、回滚、再向前。

## 选项

1. 采用 `yoyo-migrations`。它有自己的版本表和文件名习惯。
2. 用标准库执行 SQL。每个切片一个目录 `backend/<slice>/migrations/`。文件名 `Vxxx__desc.sql`，回滚文件 `Vxxx__desc.down.sql`。只向前追加版本，不改已经合入的 SQL。

## 决定

选 2。这比 yoyo 更轻，不增加依赖。yoyo 因此不进入清单。若以后要换成 yoyo，另写 ADR。

- 版本表 `schema_migrations(version text primary key, applied_at timestamptz not null)` 由运行器创建，不属于业务表。
- 运行器按版本号应用全部切片里尚未执行的 `Vxxx__*.sql`，跳过 `.down.sql`。
- 全部 SQL 使用参数。SQL 只出现在适配器、迁移文件和运行器里。
- CI 在临时 PostgreSQL 中对全部已有迁移执行 up、down、up。任一步失败，检查失败。
- identity 的 `V001__init.sql` 一次建 users、sessions、students、teacher_grants、login_attempts、audit_events。`audit_events.detail_json` 是 JSONB。审计在概念上属于 kernel，为了只建一次库，表放在这次 identity 迁移里。

标识锁成 text。新行是 UUID 第 4 版规范文本。

## 后果

回滚脚本必须能删掉这次建出的表。已经合入的迁移文件不再改写。下一张表用下一个版本号。

## 状态

采纳。2026-11-18。
