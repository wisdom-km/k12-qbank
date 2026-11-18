# 实现矩阵

日期：2026-11-18。六行是 ADR 0004 的六个切片。只记仓库里已经有的实现。

identity 与审计的迁移是 `backend/identity/migrations/V001__init.sql`。`K12_ENV` 默认 development。development 且 `K12_PG_DSN` 为空时进程仍用内存。production 没有连接串就退出。题目表和答案表没有建。内存适配器不是持久适配器。`MemoryFiles` 只在进程内存里放字节，不是磁盘或对象存储。一个端口要同时有内存实现和至少一个持久实现，并且契约测试两边都跑，才算真接缝。

2026-11-18 的决定：真实库只用 PostgreSQL，不做 SQLite 过渡。identity 和审计是第一次有行要写的表。题目表和答案表仍没有行，不建。同一天晚些时候，这两行的内存适配器和 PostgreSQL 适配器已经接上。没有 `K12_PG_DSN` 时，现有合成检查不连接数据库。HTTP 上的出卷老师来自会话 cookie。practice 仍只调用 Authorizer，不导入 identity。网页路由是 `/login`、`/`、`/admin` 和 `/account`。未登录打开受保护页会去 `/login`。

日志的 `StdoutLogger` 在组合根，不属于这六个切片。审计写入是独立的一行，不是第七个切片。`FileLog` 按日写 `runtime-YYYYMMDD.jsonl`，单文件超过 50MB 再切，并写 `log_rotation`。标准输出始终打开。

M-14：`GET /api/admin/errors` 只读近 24 小时的 ERROR。`K12_ERROR_WEBHOOK_URL` 为空时不向外发送。外部接收方仍未对接。每个响应默认带 Content-Security-Policy 和 Permissions-Policy。`K12_SECURITY_HEADERS=0` 关闭这两项。

2026-11-18：ADR 0032 到 0038 的代码已接上。ADR 0039 的六张表和适配器已接上。题目规范化表仍不建。`/health` 仍只表示进程还在。`/health/ready` 才检查数据库和迁移。

契约测试指：每个端口一套测试，假适配器和真实适配器都跑。草稿形状的 schema 测试算 core 测试，不算这一列。identity 与审计的一次本机走查写在 `docs/evidence/identity-audit-2026-11-18.md`。catalog 与 practice 的一次本机走查写在 `docs/evidence/catalog-practice-pg-2026-11-18.md`。这两页都不是试用，也不是 AC-01。`test_http_loop` 是本机合成 HTTP，不是端到端。

改了某一格，同一个 PR 里改本表，并勾选 PR 模板里的对应项。

| 切片 | 端口 | 内存适配器 | 持久适配器 | core 测试 | 契约测试 | 端到端 | 文档 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| catalog | 题目草稿、答案草稿、核准写入 | `MemoryDrafts`、`MemoryAnswers`、`MemoryApprovals` | `PgApprovals`。连接由 `K12_PG_DSN` 注入 | `test_question_draft`、`test_import_draft`、`test_import_answer`、`test_contract_schema`、`test_review_import` | `test_catalog_practice_contract`。内存每次都跑。PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套 | `docs/evidence/catalog-practice-pg-2026-11-18.md` | ADR 0013、0014、0017、0018、0039。0039 的运行表已接上。规范化题目表未建 |
| knowledge | 文档里有查询知识点。代码里没有 | 无 | 无 | 无 | 未写 | 未写 | ADR 0015、0016。切片目录未建 |
| identity | 会话、用户、学生、授权。practice 仍只通过 Authorizer 读授权结果 | `MemoryDb` | `PgDb`。连接由 `K12_PG_DSN` 注入 | `tests/identity` | 内存每次都跑。PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套 | `docs/evidence/identity-audit-2026-11-18.md` | ADR 0025、0026、0027、0028、0029、0033、0034、0036、0038。0033 的清理、0034 的咨询锁、0036 的首次改口令和 0038 的最后一名管理员已接上 |
| audit | 审计写入、审计查询、近期 ERROR | `MemoryAuditBook`、`ErrorRing` | `AuditPg` 写 `audit_events`。表在 identity 的 V001 | `test_audit_sink`、`tests/identity` | 内存每次都跑。PostgreSQL 与 identity 同一套 | 同上。webhook 仍空 | ADR 0030、0037。0037 的读审计已接上。不是 ADR 0004 的第七个切片 |
| practice | 练习存储、文件、单页渲染、授权 | `MemoryPractice`、`MemoryFiles`、`MemoryAuth`。`StdPdf` 是标准库渲染，不是存储。拉丁用 Helvetica，中文用本机楷体 | `PgPractice` / `PgFiles`。页字节在 `K12_FILE_DIR`。目录为空时字节仍在内存 | `test_core_loop`、`test_paper_status`、`test_confirm_rules`、`test_http_loop`、`test_m1_review`、`test_service_probe`、`test_kaiti_page` | `test_catalog_practice_contract`。内存每次都跑。PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套 | `docs/evidence/catalog-practice-pg-2026-11-18.md` | ADR 0006、0015、0024、0039。0039 的运行表已接上。规范化练习册表未建 |
| analysis | 作答分析、练习推荐、任务。只在架构文档 | 无 | 无 | 无 | 未写 | 未写 | ADR 0005、0016。切片目录未建 |
| delivery | 排版和导出。代码里没有这个切片 | 无。面向学生的单页 PDF 在 practice 的 `StdPdf` | 无 | 无 | 未写 | 未写 | ADR 0004。切片目录未建 |
