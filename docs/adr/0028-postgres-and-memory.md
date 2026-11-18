# ADR 0028 内存和 PostgreSQL

状态：accepted

## 背景

ADR 0012 把关系数据库定为 PostgreSQL。ADR 0019 拒绝用 SQLite 当过渡。identity 和审计现在有行要写。题目、答案、发布和知识点仍然没有要写入的行。

## 选项

1. 先用 SQLite 文件把行写出来，以后再迁到 PostgreSQL。
2. 测试和合成用内存适配器。真实写入用 PostgreSQL。不引入 SQLite。
3. 第一次连接时把 ADR 0013 到 0016 的空表一起建上。

## 决定

选 2。

- 内存适配器只给测试和合成路径。PostgreSQL 是唯一的真实库。
- 不增加 SQLite 驱动，不建 SQLite 文件，不把 SQLite 写成过渡步骤。ADR 0019 的正文保留，不改原句。本条确认那条「不做 SQLite」的决定已经落到第一次真实写入。
- 本地开发用 `docker compose -f docker/compose.yml up -d` 启动 `postgres:16`。账号口令只用于本机。
- 连接串从 `K12_PG_DSN` 注入组合根。用例和 domain 不导入 `psycopg`。
- 连接池是 `psycopg_pool.ConnectionPool`。`K12_PG_POOL_MIN` 和 `K12_PG_POOL_MAX` 控制大小。`psycopg[binary]` 是已预批准的驱动。连接池在独立发行包 `psycopg_pool`，与该驱动的 pool extra 是同一个库，版本钉死。
- 一个用例一个事务。跨切片不共享事务。
- 失败返回 `Err`。业务拒绝不抛异常。连接失败或未预期的数据库错误映射为 `store_failed`。唯一约束冲突映射为 `username_taken` 或 `already_granted`。
- 标识用 text。新行使用 UUID 第 4 版的规范文本。合成夹具沿用已有的 `teacher-synth` 和 `student-synth`，避免改写已冻结的卷面学号。
- 这次只建有行要写的表：users、sessions、students、teacher_grants、login_attempts、audit_events。题目表和答案表仍按 ADR 0013 和 0014，有行时再在同一次改动里建。本条不改 ADR 0012 的正文。

待确认：若必须在这次把题目表一起建出来，请否决本条的最后一点。当前按「只建有行要写的表」执行。

## 后果

`K12_PG_DSN` 为空时，进程使用内存适配器，现有合成检查不必启动数据库。变量有值时，启动要连上 PostgreSQL，否则在标准输出打一条 ERROR 并以非 0 退出。

## 状态

采纳。2026-11-18。不取代 ADR 0012。ADR 0019 仍是 accepted。
