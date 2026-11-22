# 实现矩阵

日期：2026-11-18。六行是 ADR 0004 的六个切片。只记仓库里已经有的实现。

identity 与审计的迁移是 `backend/identity/migrations/V001__init.sql`。`K12_ENV` 默认 development。development 且 `K12_PG_DSN` 为空时进程仍用内存。production 没有连接串就退出。规范化题目表和答案表的迁移是 `backend/catalog/migrations/V004__questions_answers.sql`。子表迁移是 `backend/catalog/migrations/V005__catalog_subtables.sql`。内存适配器不是持久适配器。`MemoryFiles` 只在进程内存里放字节，不是磁盘或对象存储。一个端口要同时有内存实现和至少一个持久实现，并且契约测试两边都跑，才算真接缝。

2026-11-18 的决定：真实库只用 PostgreSQL，不做 SQLite 过渡。identity 和审计是第一次有行要写的表。题目表和答案表仍没有行，不建。同一天晚些时候，这两行的内存适配器和 PostgreSQL 适配器已经接上。没有 `K12_PG_DSN` 时，现有合成检查不连接数据库。HTTP 上的出卷老师来自会话 cookie。practice 仍只调用 Authorizer，不导入 identity。网页路由是 `/login`、`/`、`/admin` 和 `/account`。未登录打开受保护页会去 `/login`。`K12_OPENAPI` 默认关闭。只有值为 1 时进程才打开 `/docs` 和 `/openapi.json`。`K12_ENV=production` 时不加载合成账号。

日志的 `StdoutLogger` 在组合根，不属于这六个切片。审计写入是独立的一行，不是第七个切片。`FileLog` 按日写 `runtime-YYYYMMDD.jsonl`，单文件超过 50MB 再切，并写 `log_rotation`。标准输出始终打开。

M-14：`GET /api/admin/errors` 只读近 24 小时的 ERROR。`K12_ERROR_WEBHOOK_URL` 为空时不向外发送。地址非空时异步 POST time、request_id、module、event、outcome，超时 2 秒，最多重试 1 次，失败只打一条 WARN。外部接收方仍未对接，M-14 仍未通过。每个响应默认带 Content-Security-Policy 和 Permissions-Policy。`K12_SECURITY_HEADERS=0` 关闭这两项。

2026-11-18：ADR 0032 到 0038 的代码已接上。ADR 0039 的六张表和适配器已接上。题目规范化表仍不建。`/health` 仍只表示进程还在。`/health/ready` 才检查数据库和迁移。

2026-11-19：V004 建 `questions` 和 `answers`。两边都核准时插入一行，已有 `question_id` 不覆盖。子表仍未建。

2026-11-20：V005 建 `question_option`、`sub_question`、`question_asset`、`answer_part`、`answer_asset`。核准快照带真实题型时写入题目行和答案行，不再写 `unresolved`。已有 `question_id` 不覆盖。`figure_geometry` 和 `answer_decision` 仍未建。同一天，knowledge 的内存端口已接。知识点表和解题方法表仍未建。

2026-11-21：V006 建 `practice_item`。多题卷按 `order_no` 冻结。`papers.question_version_id` 仍保留，写入时抄传入序列的第一条。适用答案不新增 catalog 端口，沿用核准快照上绑定的 `answer_version_id`。

2026-11-21：V007 建 `publication`。双方都核准且未 retired 的 approval 补一条 active。`layout_template_id` 仍无读写。retire 动作和 `publication_asset` 仍未做。

2026-11-22：HTTP 出卷传入 `publications`。端口 `retire_by_binding` 已落地，只在真正撤销时写审计。retire HTTP 路由和 `publication_asset` 仍未做。端口不校验 admin 角色，见 issue #66。

契约测试指：每个端口一套测试，假适配器和真实适配器都跑。草稿形状的 schema 测试算 core 测试，不算这一列。identity 与审计的一次本机走查写在 `docs/evidence/identity-audit-2026-11-18.md`。catalog 与 practice 的一次本机走查写在 `docs/evidence/catalog-practice-pg-2026-11-18.md`。这两页都不是试用，也不是 AC-01。`test_http_loop` 是本机合成 HTTP，不是端到端。

改了某一格，同一个 PR 里改本表，并勾选 PR 模板里的对应项。

| 切片 | 端口 | 内存适配器 | 持久适配器 | core 测试 | 契约测试 | 端到端 | 文档 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| catalog | 题目草稿、答案草稿、核准写入、`Publications` | `MemoryDrafts`、`MemoryAnswers`、`MemoryApprovals`、`MemoryPublications` | `PgApprovals`、`PgPublications`、`PgQuestions`、`PgAnswers`、`PgSubQuestions`、`PgQuestionOptions`、`PgQuestionAssets`、`PgAnswerParts`、`PgAnswerAssets`。连接由 `K12_PG_DSN` 注入 | `test_question_draft`、`test_import_draft`、`test_import_answer`、`test_contract_schema`、`test_review_import` | `test_catalog_practice_contract`、`tests/catalog/test_publications_contract`。内存每次都跑。PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套 | `docs/evidence/catalog-practice-pg-2026-11-18.md`、`docs/evidence/catalog-normalized-tables-2026-11-19.md`、`docs/evidence/catalog-subtables-2026-11-20.md`、`docs/evidence/publication-table-2026-11-21.md` | ADR 0013、0014、0017、0018、0039。0039 的运行表已接上。V004 的 `questions` 和 `answers` 已接上。V005 的五张子表已接上。`figure_geometry`、`answer_decision` 仍未建。ADR 0015 publication 已接。端口 retire 已落地，不含 retire HTTP 路由、publication_asset、layout 绑定。HTTP 出卷已传 publications |
| knowledge | `KnowledgePoints`、`Methods`、`QuestionTagger`。只读接缝是 `CatalogReader` | `MemoryKnowledgePoints`、`MemoryMethods`、`MemoryTagger` | 未接 | `test_knowledge_point_crud`、`test_method_crud`、`test_tagger_rules`、`test_catalog_seam` | `test_knowledge_contract`。内存每次都跑。PostgreSQL 分支预留未写 | 未写 | ADR 0015、0016。端口和内存实现已接。表未建 |
| identity | 会话、用户、学生、授权。practice 仍只通过 Authorizer 读授权结果 | `MemoryDb` | `PgDb`。连接由 `K12_PG_DSN` 注入 | `tests/identity` | 内存每次都跑。PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套 | `docs/evidence/identity-audit-2026-11-18.md` | ADR 0025、0026、0027、0028、0029、0033、0034、0036、0038。0033 的清理、0034 的咨询锁、0036 的首次改口令和 0038 的最后一名管理员已接上 |
| audit | 审计写入、审计查询、近期 ERROR | `MemoryAuditBook`、`ErrorRing` | `AuditPg` 写 `audit_events`。表在 identity 的 V001 | `test_audit_sink`、`tests/identity`、`test_error_webhook` | 内存每次都跑。PostgreSQL 与 identity 同一套 | 同上。地址非空时 webhook 发送五个字段。外部接收方仍未对接 | ADR 0030、0037。0037 的读审计已接上。不是 ADR 0004 的第七个切片 |
| practice | 练习存储、文件、单页渲染、授权、`PracticeItems` | `MemoryPractice`、`MemoryPracticeItems`、`MemoryFiles`、`MemoryAuth`。`StdPdf` 是标准库渲染，不是存储。拉丁用 Helvetica，中文用本机楷体 | `PgPractice` / `PgPracticeItems` / `PgFiles`。页字节在 `K12_FILE_DIR`。目录为空时字节仍在内存 | `test_core_loop`、`test_paper_status`、`test_confirm_rules`、`test_http_loop`、`test_m1_review`、`test_service_probe`、`test_kaiti_page` | `test_catalog_practice_contract`、`tests/practice/test_practice_item_contract`。内存每次都跑。PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套 | `docs/evidence/catalog-practice-pg-2026-11-18.md`、`docs/evidence/practice-item-2026-11-21.md` | ADR 0006、0015、0024、0039。0039 的运行表已接上。ADR 0015 第 7 条 `practice_item` 已接。旧 `papers.question_version_id` 保留作兼容 |
| analysis | 作答分析、练习推荐、任务。只在架构文档 | 无 | 无 | 无 | 未写 | 未写 | ADR 0005、0016。切片目录未建 |
| delivery | 排版和导出。代码里没有这个切片 | 无。面向学生的单页 PDF 在 practice 的 `StdPdf` | 无 | 无 | 未写 | 未写 | ADR 0004。切片目录未建 |
