# 实现矩阵

日期：2026-11-23。下面按日保留过程。当前状态以本节末的表为准。六行是 ADR 0004 的六个切片。只记仓库里已经有的实现。

identity 与审计的迁移是 `backend/identity/migrations/V001__init.sql`。`K12_ENV` 默认 development。development 且 `K12_PG_DSN` 为空时进程仍用内存。production 没有连接串就退出。规范化题目表和答案表的迁移是 `backend/catalog/migrations/V004__questions_answers.sql`。子表迁移是 `backend/catalog/migrations/V005__catalog_subtables.sql`。内存适配器不是持久适配器。`MemoryFiles` 只在进程内存里放字节，不是磁盘或对象存储。一个端口要同时有内存实现和至少一个持久实现，并且契约测试两边都跑，才算真接缝。

2026-11-18 的决定：真实库只用 PostgreSQL，不做 SQLite 过渡。identity 和审计是第一次有行要写的表。题目表和答案表仍没有行，不建。这是 2026-11-18 当天的决定。2026-11-19 的 V004 已建这两张表。同一天晚些时候，这两行的内存适配器和 PostgreSQL 适配器已经接上。没有 `K12_PG_DSN` 时，现有合成检查不连接数据库。HTTP 上的出卷老师来自会话 cookie。practice 仍只调用 Authorizer，不导入 identity。网页路由是 `/login`、`/`、`/admin` 和 `/account`。未登录打开受保护页会去 `/login`。`K12_OPENAPI` 默认关闭。只有值为 1 时进程才打开 `/docs` 和 `/openapi.json`。`K12_ENV=production` 时不加载合成账号。

日志的 `StdoutLogger` 在组合根，不属于这六个切片。审计写入是独立的一行，不是第七个切片。`FileLog` 按日写 `runtime-YYYYMMDD.jsonl`，单文件超过 50MB 再切，并写 `log_rotation`。标准输出始终打开。

M-14：`GET /api/admin/errors` 只读近 24 小时的 ERROR。`K12_ERROR_WEBHOOK_URL` 为空时不向外发送。地址非空时异步 POST time、request_id、module、event、outcome，超时 2 秒，最多重试 1 次，失败只打一条 WARN。外部接收方仍未对接，M-14 仍未通过。每个响应默认带 Content-Security-Policy 和 Permissions-Policy。`K12_SECURITY_HEADERS=0` 关闭这两项。

2026-11-18：ADR 0032 到 0038 的代码已接上。ADR 0039 的六张表和适配器已接上。2026-11-18 当日，题目规范化表尚未建。见 2026-11-19 段。`/health` 仍只表示进程还在。`/health/ready` 才检查数据库和迁移。

2026-11-19：V004 建 `questions` 和 `answers`。两边都核准时插入一行，已有 `question_id` 不覆盖。2026-11-19 当日，子表尚未建。见 2026-11-20 段。

2026-11-20：V005 建 `question_option`、`sub_question`、`question_asset`、`answer_part`、`answer_asset`。核准快照带真实题型时写入题目行和答案行，不再写 `unresolved`。已有 `question_id` 不覆盖。`figure_geometry` 和 `answer_decision` 仍未建。同一天，knowledge 的内存端口已接。知识点表和解题方法表仍未建。

2026-11-21：V006 建 `practice_item`。多题卷按 `order_no` 冻结。`papers.question_version_id` 仍保留，写入时抄传入序列的第一条。适用答案不新增 catalog 端口，沿用核准快照上绑定的 `answer_version_id`。

2026-11-21：V007 建 `publication`。双方都核准且未 retired 的 approval 补一条 active。`layout_template_id` 仍无读写。2026-11-21 当日，retire 路由和 `publication_asset` 尚未做。见 2026-11-22 与 2026-11-23 段。

2026-11-22：HTTP 出卷传入 `publications`。端口 `retire_by_binding` 已落地，只在真正撤销时写审计。端口不校验 admin 角色。issue #66 已由 PR #68 关闭。管理员路由第一句是 `admin_only`。

2026-11-22：管理员路由 `POST /api/admin/publications/retire` 与 `POST /api/admin/publications/publish`。路由第一句是 `admin_only`。显式 publish 从 approvals 读 `subject_id`，`layout_template_id` 去空白后写入，空则 NULL。`publication_id` 为 `pub-{q}-{a}-{seq}`。只在真正 published 时写 `publication_published`。端口仍不校验角色。2026-11-22 当日，`publication_asset` 尚未做。issue #66 已关闭。资产见下一段 V008。

2026-11-23：`Publications.list_page` 与 `GET /api/admin/publications`。过滤、offset、limit 都可选。`status` 只有 `active` 和 `retired`。排序只按 `publication_id`。端口不看角色，路由第一句是 `admin_only`。成功读取不写审计。列出发布记录的当日，`publication_asset` 尚未做。同日稍后的 V008 已建该表。

2026-11-23：V008 建 `publication_asset`。端口 `attach_asset`、`remove_asset`、`list_assets`。管理员路由是 `POST`、`DELETE`、`GET /api/admin/publications/{publication_id}/assets`。路由第一句是 `admin_only`。真正挂上写 `publication_asset_attached`，真正卸下写 `publication_asset_removed`。列出资产不写审计。字节上传仍未做。迁移锁仍由运行器持有，不写进 SQL 文件。

2026-11-23：V009 用部分唯一索引 `publication_one_active` 换下 `publication_binding_unique`。同一绑定可以有多条 `retired`，至多一条 `active`。retire 审计的 `target_id` 来自 `UPDATE … RETURNING publication_id`。

2026-11-24：V011 给 `papers` 增加 `qr_printed` 和 `printed_external_id`，给 `practice_item` 增加 `stem_text` 和 `answer_text`。HTTP 出卷在请求体带两道及以上已核准题目时走多题。每题一页，页上印出卷时抄下的学号、页码、二维码、定位标记和固定答题框。`K12_PAPER_QR=off` 当次不印码，已发出的卷保留出卷时的开关。收卷和识别仍未做。

2026-11-24：V012 给 `papers` 增加 `slots_per_page`，给 `practice_item` 增加 `page_no`、`slot_no`、`slot_span`、`option_text`。当时的新卷是每页 4 个等高槽位。

2026-11-24：V013 给 `approvals` 增加可空的 `answer_space`，不回填已有行。给 `papers` 增加 `layout_kind`（默认 `slots`）和 `layout_params`，给 `practice_item` 增加 `placed_lines`，并新建 `practice_item_box`。新的 HTTP 出卷按题型高度排版（`layout_kind=flow`），把每个答题框的坐标写入 `practice_item_box`。读卷和渲染只读这些坐标。`slots_per_page` 为 1 或 4 的旧卷仍走槽位代码，不重新排版。一整页放不下一道题时出卷返回 `item_too_long`，不截断。版式参数不合法时，production 启动失败，development 出卷返回 `layout_invalid`。当时收卷和识别仍未做。

2026-11-24：V014 允许 `files.purpose` 为 `intake`，不改已有 `page` 行。给 `papers` 增加可空的 `issued_on`，只在新出的卷上写入，不回填。新建 `intake_page`。同一张卷的同一页同时只有一条 `superseded_at` 为空的记录。老师页用 jsQR 读码，上传前缩小并重新编码成 JPEG。服务端核对卷号、页码和出卷老师。按题裁切和模型认学号页码仍未做。

2026-11-24：V015 建 `ai_run` 和 `ai_suggestion`。识别建议不写入 `confirmations`。转写和判断分两步。选择题以及纯数字或纯字母的填空在本机比对。模型读回的学号和页码只存 `consistent`、`mismatch` 或 `unread`。默认适配器是 mock。见 ADR 0045。

2026-11-25：V017 建 `teacher_decision`。每张卷的每道题同时只有一条未作废结论。来源是 adopted、revised、manual。不改写 `confirmations`，不改已发出的卷。批改页是 `/papers/{paper_id}/grade`。见 ADR 0047。

2026-11-25：V018 建 `book` 与 `book_lesson`。`approvals` 增加可空的 `book_id`、`pdf_page`，不回填。题目册、答案册、目录可以分开放。页码按册唯一。题目按课时的页码范围归课。新导入的 `answer_text` 带上小问。不改已发出的卷。见 ADR 0048。

契约测试指：每个端口一套测试，假适配器和真实适配器都跑。草稿形状的 schema 测试算 core 测试，不算这一列。identity 与审计的一次本机走查写在 `docs/evidence/identity-audit-2026-11-18.md`。catalog 与 practice 的一次本机走查写在 `docs/evidence/catalog-practice-pg-2026-11-18.md`。这两页都不是试用，也不是 AC-01。`test_http_loop` 是本机合成 HTTP，不是端到端。

改了某一格，同一个 PR 里改本表，并勾选 PR 模板里的对应项。

当前结论：V004–V018 已在仓库。新导入的题把文字和公式分开存。出卷按公式的真实高度排版，不印 LaTeX 源码。`formula_unsupported`、`formula_unstructured`、`formula_too_wide` 都是 409。`figure_geometry` 与 `answer_decision` 仍未建。issue #66 已于 2026-11-22 由 PR #68 关闭。资产字节上传仍未做。HTTP 出卷可以一次放入多道已核准的题，新卷按题型高度排版。收卷照片已接（V014）。识别建议已接（V015，`ai` 切片）。老师结论已接（V017，`teacher_decision`）。批改页已接。按题裁切仍未做。V018 的 `book` 与 `book_lesson` 已接。新导入写入 `approvals.book_id` 与 `pdf_page`，不回填。老师页按课时选题。见 ADR 0048。

| 切片 | 端口 | 内存适配器 | 持久适配器 | core 测试 | 契约测试 | 端到端 | 文档 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| catalog | 题目草稿、答案草稿、核准写入、`Publications` | `MemoryDrafts`、`MemoryAnswers`、`MemoryApprovals`、`MemoryPublications` | `PgApprovals`、`PgPublications`、`PgQuestions`、`PgAnswers`、`PgSubQuestions`、`PgQuestionOptions`、`PgQuestionAssets`、`PgAnswerParts`、`PgAnswerAssets`。连接由 `K12_PG_DSN` 注入 | `test_question_draft`、`test_import_draft`、`test_import_answer`、`test_contract_schema`、`test_review_import`、`test_http_publication_retire`、`test_http_publication_publish`、`tests/catalog/test_publications_list_http`、`tests/catalog/test_publication_assets_http`、`test_catalog_book_import` | `test_catalog_practice_contract`、`tests/catalog/test_publications_contract`、`tests/catalog/test_publications_list_contract`、`tests/catalog/test_publication_assets_contract`。内存每次都跑。PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套。`test_catalog_book_import` 也是内存每次都跑，PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套整书导入 | `docs/evidence/catalog-practice-pg-2026-11-18.md`、`docs/evidence/catalog-normalized-tables-2026-11-19.md`、`docs/evidence/catalog-subtables-2026-11-20.md`、`docs/evidence/publication-table-2026-11-21.md` | ADR 0013、0014、0017、0018、0039。0039 的运行表已接上。V004 的 `questions` 和 `answers` 已接上。V005 的五张子表已接上。`figure_geometry`、`answer_decision` 仍未建。ADR 0015 publication 已接。端口 retire 与 `publish_by_binding` 已落地。管理员路由 retire 与 publish 已接，第一句 `admin_only`。端口仍不校验角色。issue #66 已关闭。显式 publish 写入 trim 后的 `layout_template_id`，空则 NULL，出卷仍不读它。HTTP 出卷已传 publications。`list_page` 与 `GET /api/admin/publications` 已接。成功读取不写审计。V008 的 `publication_asset` 已接。`attach_asset`、`remove_asset`、`list_assets` 已接。三条 admin 资产路由第一句是 `admin_only`。真正挂上写 `publication_asset_attached`，真正卸下写 `publication_asset_removed`。列出资产不写审计。字节上传仍未做。整书导入是 `POST /api/admin/catalog/books/{book_id}/import`。旧路由 `POST /api/admin/catalog/drafts` 已删除。核准快照返回 `answer_space`。为空时按题型默认，并标明是默认。书清单可逐题覆盖。见 ADR 0042 修订与 ADR 0043。目录项返回 `formula_note`。没有公式片段的旧行写「公式未结构化」。整书导入对不支持的公式命令记警告 `formula_unsupported`，不挡导入。重导仍按纯文本比较，kept 的行不补片段。见 ADR 0046。V018 的 `book`、`book_lesson` 已接。`GET /api/catalog/books/{book_id}/lessons` 已接。整书导入可分题目册、答案册、目录。新导入的 `answer_text` 含小问。见 ADR 0048。core 测试另有 `test_book_volumes`、`test_book_toc`、`test_book_lessons_http`、`test_answer_text`、`test_v018_pg` |
| knowledge | `KnowledgePoints`、`Methods`、`QuestionTagger`。只读接缝是 `CatalogReader` | `MemoryKnowledgePoints`、`MemoryMethods`、`MemoryTagger` | 未接 | `test_knowledge_point_crud`、`test_method_crud`、`test_tagger_rules`、`test_catalog_seam` | `test_knowledge_contract`。内存每次都跑。PostgreSQL 分支预留未写 | 未写 | ADR 0015、0016。端口和内存实现已接。表未建 |
| identity | 会话、用户、学生、授权。practice 仍只通过 Authorizer 读授权结果 | `MemoryDb` | `PgDb`。连接由 `K12_PG_DSN` 注入 | `tests/identity` | 内存每次都跑。PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套 | `docs/evidence/identity-audit-2026-11-18.md` | ADR 0025、0026、0027、0028、0029、0033、0034、0036、0038。0033 的清理、0034 的咨询锁、0036 的首次改口令和 0038 的最后一名管理员已接上 |
| audit | 审计写入、审计查询、近期 ERROR | `MemoryAuditBook`、`ErrorRing` | `AuditPg` 写 `audit_events`。表在 identity 的 V001 | `test_audit_sink`、`tests/identity`、`test_error_webhook` | 内存每次都跑。PostgreSQL 与 identity 同一套 | 同上。地址非空时 webhook 发送五个字段。外部接收方仍未对接 | ADR 0030、0037。0037 的读审计已接上。不是 ADR 0004 的第七个切片 |
| practice | 练习存储、文件、卷面渲染、授权、`PracticeItems`、老师结论 | `MemoryPractice`、`MemoryPracticeItems`、`MemoryFiles`、`MemoryIntake`、`MemoryAuth`、`MemoryDecisions`。`StdPdf` 是标准库渲染，不是存储。拉丁用 Helvetica，中文用部署环境的字体 | `PgPractice` / `PgPracticeItems` / `PgFiles` / `PgIntake` / `PgDecisions`。页字节在 `K12_FILE_DIR`。目录为空时字节仍在内存 | `test_core_loop`、`test_paper_status`、`test_confirm_rules`、`test_http_loop`、`test_m1_review`、`test_service_probe`、`test_kaiti_page`、`test_multi_paper`、`test_paper_slots`、`test_paper_face_boundary`、`test_flow_layout`、`test_formula_layout`、`test_formula_pg`、`tests/practice/test_qr_code`、`test_intake_http`、`test_intake_pg`、`test_decision`、`test_decision_http`、`test_decision_pg` | `test_catalog_practice_contract`、`tests/practice/test_practice_item_contract`。内存每次都跑。PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套 | `docs/evidence/catalog-practice-pg-2026-11-18.md`、`docs/evidence/practice-item-2026-11-21.md` | ADR 0006、0015、0024、0039、0043。0039 的运行表已接上。ADR 0015 第 7 条 `practice_item` 已接。V013 的 `practice_item_box` 已接。新卷 `layout_kind` 为 `flow`。旧 `papers.question_version_id` 保留作兼容。`slots_per_page` 为 1 或 4 的卷不重排。V014 的 `intake_page` 已接。收卷照片 purpose 为 `intake`。`publication_asset` 拒绝 intake 文件。见 ADR 0041、0044、0046、0047。V016 的 `stem_parts`、`option_parts`、`formula_draw` 可空，不回填。新卷把排好的字形和分数线冻进 `formula_draw`。再打开时不重新排版。不支持的命令、未结构化的旧公式、比一行宽的公式分别是 `formula_unsupported`、`formula_unstructured`、`formula_too_wide`。V017 的 `teacher_decision` 已接。每题同时一条未作废结论。`\textcircled{1}` 到 `\textcircled{20}` 排成圆圈序号。缺字形是 `not_rendered`。见 ADR 0046 修订
| ai | `VisionModel`。`transcribe` 与 `judge` | `MockModel`、`MemoryRuns` | `VolcengineModel` 用已钉死的 httpx。`PgRuns` 在 `K12_PG_DSN` 有值时接入。默认 provider 是 mock | `test_ai_grade`、`test_ai_flow`、`test_ai_http`、`test_ai_provider`、`test_ai_volcengine` | `test_ai_pg`。内存每次都跑前面的 core。PostgreSQL 在 `K12_PG_DSN` 有值时跑 V015 的 up / down / up。火山引擎适配器用本机假 HTTP，不连外网 | 老师页只读建议见 `apps/web/tests/ai_panel.test.jsx`。真实样张识别率未测 | ADR 0045。建议不进确认表。按题裁切仍未做。采用、改判和手评见 ADR 0047 |
| analysis | 作答分析、练习推荐、任务。只在架构文档 | 无 | 无 | 无 | 未写 | 未写 | ADR 0005、0016。切片目录未建 |
| delivery | 排版和导出。代码里没有这个切片 | 无。面向学生的单页 PDF 在 practice 的 `StdPdf` | 无 | 无 | 未写 | 未写 | ADR 0004。切片目录未建 |
