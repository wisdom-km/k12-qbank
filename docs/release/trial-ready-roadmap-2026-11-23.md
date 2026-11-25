# 试用就绪路线图（2026-11-23）

盘点日：2026-11-23。基线 `origin/main` 为 `dffee8e`（Merge pull request #81）。本文件只做盘点。不改代码、迁移、测试、CI、ADR、`RULES.md`、`README.md`、`README.en.md`、`docs/implementation-matrix.md`。不开 issue，不产生 PR，不动 `v0.2.0` / `v0.3.0`。

前置：

| 检查 | 结果 |
| --- | --- |
| `git ls-remote --tags origin v0.3.0` | 命中 `bb63e6f956aba4bc9773476e5089abbf06cb7469` |
| `gh release view v0.3.0` 的 `isPrerelease` | `true` |
| GraphQL `release.isLatest` | `false`；`latestRelease` 为 null |
| `git log origin/main -1` | `dffee8e Merge pull request #81` |
| `gh issue list --state open` | 6 条：#28 #35 #47 #71 #73 #82 |

产品输入（本批不改写）：1 名老师、5–10 名学生、1 周、七年级上册有理数运算。闭环是核验、出卷、整页拍照收卷、一次多模态 Vision 调用、老师确认、再练习。Docker 单机，先在本机笔记本，以后可搬云主机。模型走火山引擎方舟，协议兼容 OpenAI。机构已书面同意第三方数据传输。识别不另接 OCR。卷面只印学号和页码。`files.purpose='page'` 的读取限于当堂老师和超级管理员，并写入审计。确认后 N 天归档并物理删除在线照片。传给火山引擎的题文在出站前把学号换成 `student-N`。真学号只进 `students.external_id`（此列当前不存在，见第 3 节）。

举例只用 `student-N`。不写真实姓名，不写真实学号。

## 1. 实现矩阵真实进度

矩阵在 `docs/implementation-matrix.md`。表头写六个切片，表体有七行：catalog、knowledge、identity、audit、practice、analysis、delivery。audit 那一行自己写明不是 ADR 0004 的第七个切片（矩阵第 42 行）。`backend/` 下有目录 `bootstrap`、`catalog`、`identity`、`kernel`、`knowledge`、`practice`。没有 `analysis`，没有 `delivery`，没有 `ai`。

迁移文件（本批列目录核对）：

| 版本 | 文件 | 引入提交 |
| --- | --- | --- |
| V001 | `backend/identity/migrations/V001__init.sql` | identity / 审计 |
| V003 | `backend/identity/migrations/V003__must_change.sql` | 首次改口令 |
| V002 | `backend/catalog/migrations/V002__catalog_practice.sql` | approvals、papers、paper_pages、attempts、confirmations、files |
| V004 | `backend/catalog/migrations/V004__questions_answers.sql` | `c4d264a` |
| V005 | `backend/catalog/migrations/V005__catalog_subtables.sql` | `8457de4` |
| V006 | `backend/catalog/migrations/V006__practice_item.sql` | `486cab0`（PR #63，合并 `f7343ee`） |
| V007 | `backend/catalog/migrations/V007__publication.sql` | `a2b8a92`（PR #64，合并 `d44fe1f`） |
| V008 | `backend/catalog/migrations/V008__publication_asset.sql` | `8a8e6b8`（PR #76，合并 `2b9ffad`） |
| V009 | `backend/catalog/migrations/V009__publication_partial_unique.sql` | `c73578c`（PR #77，合并 `c62e439`） |

没有 `figure_geometry` 迁移，没有 `answer_decision` 迁移。README 第 9 行和矩阵第 17 行、第 39 行里的「这两张表仍未建」与目录一致，不是过时句。

本批没有重跑测试。下面「测试」列只记录矩阵点名、以及本批打开过的文件。

### catalog：部分完成

端口在 `backend/catalog/application/`：`import_draft.py`、`import_answer.py`、`approved_question.py`、`publish_version.py`、`read_snapshot.py`、`ensure_publication.py`、`publish_publication.py`、`retire_publication.py`、`list_publications.py`、`attach_publication_asset.py`、`list_publication_assets.py`、`remove_publication_asset.py`。

持久适配器由 `backend/bootstrap/pg_runtime.py` 的 `open_postgres` 在 `K12_PG_DSN` 有值时接上。矩阵第 39 行点名 `PgApprovals`、`PgPublications`、`PgQuestions`、`PgAnswers` 和五张子表适配器。内存侧点名 `MemoryDrafts`、`MemoryAnswers`、`MemoryApprovals`、`MemoryPublications`。

HTTP：

| 路由 | 位置 |
| --- | --- |
| `GET/POST /api/catalog/{question_version_id}` 及 publish、revise、retire | `backend/bootstrap/routes_catalog.py:21-53` |
| `GET /api/admin/publications` | `backend/bootstrap/routes_admin.py:129` |
| `POST /api/admin/publications/retire` | 同文件第 244 行 |
| `POST /api/admin/publications/publish` | 同文件第 280 行 |
| 资产 `POST` / `DELETE` / `GET .../assets` | 同文件第 160、198、229 行 |

老师页「核准并发布」调用 catalog publish（`apps/web/src/teacher_page.jsx:61-68`）。页上只有会话给出的一道题（`apps/web/src/paper_loop.js:71-76`）。没有题目列表，没有 HTTP 草稿导入。

已完成：V004、V005、发布账本 V007、资产元数据 V008、部分唯一索引 V009、管理员列表和 retire/publish。资产挂接拒绝页文件：`backend/catalog/domain/publication.py:122-138` 对 `file-` 前缀和 `page_file` 返回 `page_file_rejected`。契约在 `tests/catalog/test_publication_assets_contract.py:97-111`，HTTP 映射在 `tests/catalog/test_publication_assets_http.py:74`。

未做：`figure_geometry`、`answer_decision`、资产字节上传（矩阵第 29 行仍写「字节上传仍未做」，与代码里只有元数据路由一致）、把真实题册批量送进老师可核验的列表。

### knowledge：部分完成（仅内存）

端口在 `backend/knowledge/ports.py`（`KnowledgePoints` 从第 37 行起，同文件还有 `Methods`、`QuestionTagger`、`CatalogReader`）。适配器只有 `backend/knowledge/memory.py`。没有 `backend/knowledge` 迁移目录，没有 PostgreSQL 适配器，没有 HTTP 路由。矩阵第 40 行写「表未建」「PostgreSQL 分支预留未写」，与目录一致。

### identity：大部分完成，学号列未按试用策略落地

端口在 `backend/identity/application/`：`login.py`、`sessions.py`、`students.py`、`teachers.py`、`grants.py`、`guard.py`、`bootstrap_admin.py`、`passwords.py`。HTTP 在 `routes_session.py:33-50` 和 `routes_admin.py:77-122`。

`students` 表在 `V001__init.sql:35-45`：`student_id` 主键，`name` 非空，另有 `grade`、`subject_id`、`status`、`created_by`、时间戳。没有 `external_id`。管理员响应把 `name` 和 `student_id` 一起返回（`routes_admin.py:492-498`）。

已完成：会话 cookie、CSRF、老师/学生/授权、引导管理员、首次改口令（V003）、PostgreSQL 与内存两套。未做：试用要求的 `external_id`、API 只返回 `student-N`、卷面学号与内部序号分开。

### audit：部分完成

写入在 `backend/bootstrap/audit_pg.py`，表是 V001 的 `audit_events`（`V001__init.sql:76-88`）。查询路由 `GET /api/admin/audit`（`routes_admin.py:125`）。近期 ERROR 是 `ErrorRing`（`backend/bootstrap/error_ring.py`）和 `GET /api/admin/errors`（`routes_observability.py:32`）。

Webhook：`K12_ERROR_WEBHOOK_URL` 为空则不发送（`error_ring.py:60-63`，`.env.example:60-62`）。非空时只 POST `time`、`request_id`、`module`、`event`、`outcome`（`error_ring.py:16`、第 49 行）。超时 2 秒，最多 2 次尝试，失败打 `webhook_failed`。外部接收方没有。issue #47 仍 OPEN。M-14 仍未通过。这和矩阵第 11 行、第 42 行一致。

成功读取练习文件不写审计。`read_file` 在授权通过后直接返回字节（`backend/practice/application/render_paper.py:152-195`）。

### practice：部分完成

端口在 `backend/practice/application/`：`issue_paper.py`、`open_paper.py`、`render_paper.py`、`confirm_attempt.py`、`compose_multi.py`、`resolve_items.py`、`visible.py`、`ports.py`。

HTTP（`routes_practice.py`）：

| 路由 | 行 |
| --- | --- |
| `GET /api/practice/papers` | 38 |
| `GET /api/practice/confirmations/count` | 44 |
| `POST /api/practice/papers` | 50 |
| `POST /api/practice/papers/{paper_id}/handout` | 54 |
| `GET /api/practice/papers/{paper_id}/attempt` | 58 |
| `GET /api/practice/files/{file_id}` | 62 |
| `POST /api/practice/confirmations` | 66 |

`IssueBody` 只有一个 `question_version_id`（`routes_practice.py:19-24`）。多题冻结函数 `compose_multi_item_paper` 定义在 `compose_multi.py:15`。仓库内调用点只有该定义和 `tests/practice/test_practice_item_contract.py:20`、第 384 行。出卷 HTTP 不调用它。

渲染写死一页，并且只用解析结果的第一题（`render_paper.py:40-50`，`page_number=1`，`page_count=1`）。页面目没有姓名字段（`backend/practice/domain/page_face.py:1-19`）。PDF 画出的是 `student ` 加 `student_id`（`backend/practice/adapters/pdf_page.py:31`）。

确认决定只接受 `adopt`、`revise`、`reject`（`backend/practice/domain/confirm.py:78-84`）。作答文本来自合成夹具 `synthetic_attempt_text()`（`routes_practice.py:90`）。没有照片上传路由。

`files.purpose` 在练习适配器里固定为 `page`（`backend/practice/adapters/pg_files.py:16`），存的是已渲染 PDF 的元数据。字节在 `K12_FILE_DIR`，表只有 `file_id`、`purpose`、`checksum`（`V002__catalog_practice.sql:72-76`）。

V006 的 `practice_item` 已建。HTTP 出卷仍是一卷一题、一页 PDF。

### analysis：未做

没有切片目录，没有端口，没有路由，没有测试。矩阵第 44 行与目录一致。

### delivery：未做

没有切片目录。面向学生的单页 PDF 在 practice 的 `StdPdf`，矩阵第 45 行与此一致。

### 一行完成度

| 切片 | 完成度 |
| --- | --- |
| catalog | 部分。发布账本、资产元数据、核准 HTTP 已接。无题库列表，无字节上传，无 `figure_geometry` / `answer_decision` |
| knowledge | 部分。只有内存端口。无表、无 PostgreSQL、无 HTTP |
| identity | 大部分。会话、学生、授权、引导管理员已接。无 `external_id`，`name` 仍必填并出现在管理员响应里 |
| audit | 部分。写入、查询、webhook 发送端已接。无外部接收方。练习文件成功读取不写审计 |
| practice | 部分。HTTP 仍是一道题、一页 PDF、合成作答、老师确认。多题表和 `compose_multi` 已有，未接到出卷路由。无收卷照片 |
| analysis | 未做 |
| delivery | 未做。单页 PDF 留在 practice |

## 1b. README 与矩阵过时清单

这是以后 Batch R0 的输入。本批不改这两份文件，也不改 `README.en.md`。英文副本和中文同一事实的过时句列在下面，建议同一个 XS PR 一起改，避免中英再分叉。

仍准确、不进入清单：`figure_geometry` 与 `answer_decision` 仍未建（README 第 9 行、第 70 行；矩阵第 17 行）。knowledge 表未建（README 第 73 行；矩阵第 40 行）。HTTP 路径仍生成单页 PDF（README 第 60 行；`render_paper.py:45-50`）。

### README.md（5 条）

1. 位置：`README.md:53`。原文：「规范化题目表仍按 ADR 0013，有行再建。规范化答案表仍按 ADR 0014，有行再建。」过时点：V004 引入提交 `c4d264a`（PR #57），V005 引入提交 `8457de4`（PR #58）。建议改为：「V004 已建 `questions` 和 `answers`。V005 已建五张子表。`figure_geometry` 和 `answer_decision` 仍未建。没有要写入的行时，不为这两张未建表加空迁移。」

2. 位置：`README.md:66`。原文：「设置 `K12_PG_DSN` 时写入 V002 的运行表，V004 的 `questions` 和 `answers`，以及 V005 的五张子表。`figure_geometry` 和 `answer_decision` 仍未建。」过时点：漏了 V007–V009（提交 `a2b8a92`、`8a8e6b8`、`c73578c`）。`figure_geometry` 半句仍准确。建议改为：「设置 `K12_PG_DSN` 时写入 V002 运行表、V004 题目和答案、V005 五张子表、V007 `publication`、V008 `publication_asset`，并应用 V009 的 `publication_one_active`。`figure_geometry` 和 `answer_decision` 仍未建。资产字节上传仍未做。」

3. 位置：`README.md:67`。原文：「设置 `K12_PG_DSN` 时写入 papers、attempts、confirmations。页字节在 `K12_FILE_DIR`。」过时点：V002 还有 `paper_pages` 和 `files`（`V002__catalog_practice.sql:35-76`），V006 还有 `practice_item`（`486cab0`）。建议改为：「设置 `K12_PG_DSN` 时写入 papers、paper_pages、attempts、confirmations、files 元数据，以及 V006 的 practice_item。页字节在 `K12_FILE_DIR`。HTTP 出卷仍只提交一道题。」

4. 位置：`README.md:72`。原文：「知识点的内存端口已接。发布记录和多题练习的表未建。现在一卷一题。」过时点：发布记录是 V007，多题表是 V006，资产表是 V008，部分唯一索引是 V009。HTTP 仍一卷一题（`routes_practice.py:19-24`）。建议改为：「知识点的内存端口已接，表未建。V006 已建 `practice_item`，V007 已建 `publication`，V008 已建 `publication_asset`，V009 已换上 `publication_one_active`。多题冻结在 `compose_multi_item_paper`，出卷 HTTP 仍只收一道题，渲染仍是一页。」

5. 位置：`README.md:126`。原文：「第一条闭环：本机合成网页。PostgreSQL 和安卓还没有。」过时点：执行计划 `docs/exec-plans/active/rational-number-loop.md:5` 已在 2026-11-18 把 PostgreSQL 指到 identity 计划；V001 起已有库表。安卓仍没有。建议改为：「第一条闭环：本机合成网页。设置 `K12_PG_DSN` 后 identity、审计、catalog、practice 会迁移。安卓还没有。」

### README.en.md（4 条）

6. 位置：`README.en.md:61`。原文：「The pages are `/login`, `/`, and `/admin`.」过时点：中文 README 第 61 行已写 `/account`。页面路由在 `apps/web/src/routes.jsx:25`，老师页链接在 `teacher_page.jsx:82`。建议改为：「The pages are `/login`, `/`, `/admin`, and `/account`.」

7. 位置：`README.en.md:66`。与中文第 66 行同一缺口。建议英文与上面第 2 条对齐，保留 “`figure_geometry` and `answer_decision` are still not built”。

8. 位置：`README.en.md:67`。与中文第 67 行同一缺口。建议英文与上面第 3 条对齐。

9. 位置：`README.en.md:72`。原文：「Publication and multi-item tables are not created. A paper still holds one question.」过时点同第 4 条。建议改为：「V006 creates `practice_item`. V007 creates `publication`. V008 creates `publication_asset`. V009 adds `publication_one_active`. `compose_multi_item_paper` can freeze several items. The issue HTTP body still sends one question, and the renderer still draws one page. Knowledge tables are not created.」

英文第 53 行已经写了 V004 和 V005，不要把它改回「有行再建」。

### docs/implementation-matrix.md（9 条）

矩阵前半是按日期追加的日记，后文已经改口。读者若停在前一段，会得到错误的当前状态。建议保留日期，把已经被后文取代的「仍未做」改成「当日尚未做」，并在第 3 行下面加一句当前结论。

10. 位置：`docs/implementation-matrix.md:3`。原文：「日期：2026-11-18。」文件正文已写到 2026-11-23（第 27–31 行）。建议改为：「日期：2026-11-23。下面按日保留过程。当前状态以本节末的表为准。」并在表前加当前结论：「V004–V009 已在仓库。`figure_geometry` 与 `answer_decision` 仍未建。issue #66 已于 2026-11-22 由 PR #68 关闭。资产字节上传仍未做。HTTP 出卷仍是一道题。」

11. 位置：第 7 行。原文含「题目表和答案表仍没有行，不建。」过时点：次日 V004（`c4d264a`）。同段后句又说适配器已接上。建议在该句后加：「这是 2026-11-18 当天的决定。2026-11-19 的 V004 已建这两张表。」

12. 位置：第 13 行。原文含「题目规范化表仍不建。」过时点：V004。建议改为：「2026-11-18 当日，题目规范化表尚未建。见 2026-11-19 段。」

13. 位置：第 15 行。原文含「子表仍未建。」过时点：V005（`8457de4`），第 17 行已经写了子表。建议改为：「2026-11-19 当日，子表尚未建。见 2026-11-20 段。」

14. 位置：第 21 行。原文含「retire 动作和 `publication_asset` 仍未做。」过时点：retire HTTP 在 PR #68，资产表在 `8a8e6b8`。建议改为：「2026-11-21 当日，retire 路由和 `publication_asset` 尚未做。见 2026-11-22 与 2026-11-23 段。」

15. 位置：第 23 行。原文含「端口不校验 admin 角色，见 issue #66。」#66 状态 CLOSED，`closedAt` 为 2026-11-22T15:19:41Z，关闭引用 PR #68。端口今天仍然不校验角色，路由校验。建议改为：「端口不校验 admin 角色。issue #66 已由 PR #68 关闭。管理员路由第一句是 `admin_only`。」

16. 位置：第 25 行。原文含「`publication_asset` 仍未做。issue #66 仍开。」两句都已过时。建议改为：「2026-11-22 当日，`publication_asset` 尚未做。issue #66 已关闭。资产见下一段 V008。」

17. 位置：第 27 行。原文含「`publication_asset` 仍未做。」同一天的第 29 行已经写 V008 已建。建议改为：「列出发布记录的当日，`publication_asset` 尚未做。同日稍后的 V008 已建该表。」

18. 位置：第 39 行 catalog 单元格。同一格先写「`publication_asset` 仍未建」，后写「V008 的 `publication_asset` 已接」。建议删掉前一处「仍未建」，保留后一处，并补上：「issue #66 已关闭。端口仍不校验角色。字节上传仍未做。`figure_geometry` 与 `answer_decision` 仍未建。」

### 1b 汇总

| 文件 | 条数 |
| --- | --- |
| `README.md` | 5 |
| `README.en.md` | 4 |
| `docs/implementation-matrix.md` | 9 |
| 合计 | 18 |

范围外、本批不放入 R0 必改，但同样会误导：`.env.example:18` 写「The normalized question tables stay unbuilt。」`ARCHITECTURE.md:47` 写「表还没建，运行模式的代码也还没改。」执行计划第 3 行仍留着 2026-11-17 的「数据库还没有」，第 5 行已另作说明。

## 2. 老师闭环五步缺口

### 步骤 1 核验题目

已有：老师页一道题的题干、答案和「核准并发布」（`teacher_page.jsx:89-108`）。服务端在双方核准前拒绝正式出卷。development 会装入合成夹具。

缺：真实题册进入正在运行的库；老师能逐题看到并核准，而不是只看到 `session.question_version_id` 那一道（`paper_loop.js:73`）。草稿导入没有 HTTP。知识点核验没有页面（knowledge 无路由）。

改动面：`apps/web/src/teacher_page.jsx`、`paper_loop.js`、一条管理员导入路径（可先做脚本，调用现有 `import_draft` / `import_answer`）、必要时 `routes_catalog.py`。不改 V001–V009 的已有文本。

批次：S。真实题若超过一页列表，再加一个 S，不并进第一刀。

### 步骤 2 出卷（PDF，试用要多题）

已有：单题出卷、单页 PDF、页面无姓名字段、PDF 印 `student_id`、V006 多题行、`compose_multi_item_paper` 及契约测试。

缺：HTTP 提交多题；渲染按题或按页画出全部题目；页码用真实 `page_count`；卷面学号来自以后的 `external_id`，响应里的内部序号是 `student-N`。当前印的就是 `student_id`（`pdf_page.py:31`）。

改动面：`routes_practice.py` 的 `IssueBody`、`open_paper.py`、`issue_paper.py`、`render_paper.py`、`pdf_page.py`、`apps/web` 出卷区。practice 不导入 catalog 适配器，继续只依赖 `backend.catalog.api`。

批次：M。依赖步骤 1 至少有两道已核准且有 active publication 的题（`compose_multi.py:34-38` 会拒绝没有 active publication 的题）。

### 步骤 3 收卷

已有：`GET /api/practice/files/{file_id}` 把已生成 PDF 交给该卷老师，且老师必须被授权（`render_paper.py:176-178`）。`purpose='page'` 今天表示这份 PDF。发布资产拒绝 page 文件。

缺：整页照片上传；一次 Vision 识别学号和作答；`purpose` 与 PDF 分开或先迁走 PDF 的 purpose（见第 5 节，须拍板）；当堂老师加超级管理员可读；成功读取写入审计。没有上传路由。没有缺页历史。安卓不在本试用的第一台机器上，本试用用浏览器选图。

改动面：新的 practice 上传用例、`routes_practice.py`、`files` 写入、`routes_admin.py` 或同一读取用例上的审计、老师页收卷区。不要把照片挂进 `publication_asset`。

批次：M。依赖步骤 2 的卷已经存在，否则没有可对照的页。

### 步骤 4 AI 建议

已有：确认接口和 `adopt` / `revise` / `reject`。作答文本是合成字符串。没有 `answer_decision` 表。没有 `backend/ai`。`.env.example` 没有火山引擎变量。`RULES.md:71` 的 A-09：未确认 DEC-03 时，不把学生卷发给真实模型。ADR 0011 第 34 行仍写模型供应商不选、开发用假适配器。

缺：`answer_decision` 或等价的建议表（本批不决定列名，实现批再对 ADR 0014）；火山引擎 Vision 适配器；mock 适配器；`K12_AI_PROVIDER`；题文出站前脱敏；失败时老师仍能手填学号并手评。

批次：表和端口 S，适配器与降级 M。两批都依赖 ADR 0041 文稿被接受，以及 A-09 的书面同意落进仓库允许的位置。mock 可以在同意落库之前用固定结果测完。真实密钥调用放在同意落库之后。

### 步骤 5 老师确认和再练习

已有：确认写 `confirmations`，相同操作键不写第二份（V002 第 68–69 行的唯一约束）。老师页有确认按钮（`teacher_page.jsx:170-201`）。

缺：确认对象今天是合成作答，不是 Vision 建议。看不清或调用失败时没有手填路径。再练习没有「从已确认记录再出一份」的页面。同类题、综合题属于 analysis，目录未建。试用的最小再练习是：老师从已核准题再出一份，不要求知识点检索。

改动面：`confirm_attempt.py`、`ConfirmBody`、`teacher_page.jsx`。再出卷复用步骤 2 的多题出卷。

批次：确认接上建议为 S。最小再练习为 S，排在多题出卷之后。知识点检索为 B，不进 A 序列。

## 3. AI Vision 适配器设计（只设计）

新包 `backend/ai/application/`，与 catalog、practice 并列。practice 依赖端口，不依赖火山引擎 SDK。本试用不新增运行时依赖：用标准库 HTTP 调用方舟的 OpenAI 兼容端点。若实现时发现必须加 SDK，先停，另写 ADR。

### 端口

`PageReading` 端口一个方法：输入一张整页图的字节、这一页的题文（已脱敏）、`detail`。输出结构：

| 字段 | 含义 |
| --- | --- |
| `student_token` | 模型读到的学号原文，只留在服务端 |
| `answers` | 逐题识别文本 |
| `suggestion` | 给老师看的建议，确认前不是正式结论 |
| `provider` | `mock` 或 `volcengine` |

调用失败返回 `Err`，码稳定，例如 `vision_unavailable`。不把异常变成「学生做错」。

### 适配器

`K12_AI_PROVIDER=mock`：不访问网络，返回固定的 `student_token`、固定作答和一句固定建议。测试只用这个。

`K12_AI_PROVIDER=volcengine`：`POST https://ark.cn-beijing.volces.com/api/v3` 的 chat completions 或 responses。图片用 `image_url` 的 data URL（base64）或方舟文档中的 `input_image`。密钥只读 `K12_VOLCENGINE_API_KEY`，不进仓库、不进日志。模型 ID 读 `K12_VOLCENGINE_MODEL`，由试用当天的控制台 ID 填入，不写死在代码里。文档页 [图片理解](https://www.volcengine.com/docs/82379/1362931)（本机保存的 Markdown 摘录，2026-11-23）给出的示例模型是 `doubao-seed-2-1-pro-260915`，base URL 为 `https://ark.cn-beijing.volces.com/api/v3`。Base64 单张小于 10 MB，请求体小于 64 MB。

配置缺省：未设置 `K12_AI_PROVIDER` 时视为 `mock`。`volcengine` 但密钥为空，启动失败并打一条不含密钥的 ERROR。production 禁止静默落到 mock。

### 学号脱敏后才传第三方 Vision

题文在离开本机之前脱敏。服务端把题文和提示词里的真学号换成这一次调用的 `student-N`，然后才把题文交给火山引擎。映射表留在本进程，不进提示词，不进日志（L-05，`RULES.md:22`）。

整页照片上印着的学号会随图片进入同一次调用。这是识别学号所必需的。返回写入 API 之前，把识别出的学号换成 `student-N`。老师页和普通 JSON 只出现 `student-N`。真学号只写入 `students.external_id`。

`external_id` 现在没有。V001 的 `students` 只有 `student_id` 和必填 `name`。实现批用新迁移添加 `external_id`，不改 V001 正文。现有 `student_id` 继续做内部主键。PDF 改印 `external_id`。在列未加之前，禁止把生产照片发给火山引擎。

### 失败降级

Vision 超时、4xx、5xx 或无法解析学号：照片仍保存，建议状态为待老师处理，确认接口保持可用。老师手填学号并选择 `adopt`、`revise` 或 `reject`。手填值只进 `external_id` 的匹配，响应仍是 `student-N`。不自动记成答错。

### Token 粗算（不是采购决定）

依据是方舟图片理解说明里的两段（摘录日期 2026-11-23）：

- doubao-seed-2.0 及以后，`detail` 默认 `high`，单图固定 1280 token。`low` 的单图范围是 [1, 1280]，`xhigh` 是 [1280, 5120]。像素超出区间时等比例缩小。
- 估算式：`min(宽 × 高 ÷ 1764, max_image_tokens)`。说明里的例子：2560×1440 算出 2090，大于 1280 就按 1280 计，并写明小字可能认不出。

一张整页 A4 的手机照片通常大于 `high` 的 2,257,920 像素，因此默认 `high` 先被缩小，图片 token 按 1280 计，不按原始像素线性增长。`xhigh` 上限在摘录里是 5120 token、像素区间到 9,031,680。本批没有把一张真实 A4 样张送进控制台 Token 计算器。

价格摘自方舟模型价格页（页面更新时间显示 2026-11-19；本机经文档镜像核对到 doubao-seed-2.0-lite 在输入长度 [0, 32] k 时输入 0.6 元/百万 token、输出 3.6 元/百万 token）。doubao-seed-2.1-pro 在模型详情摘录中是输入 6 元/百万 token、输出 30 元/百万 token。价格以调用当天控制台为准。

试用一周按 10 名学生、5 个上课日、每人每天 1 张整页、再留一倍重试，合计 100 次。题文按 1,200 token，建议输出按 800 token，且不算长思考：

| 模型与 detail | 单次大约 | 100 次大约 |
| --- | --- | --- |
| 2.0-lite，`high`（图 1280 + 文 1200） | 0.005 元 | 0.5 元 |
| 2.0-lite，`xhigh`（图按 5120 封顶） | 0.007 元 | 0.7 元 |
| 2.1-pro，`high`，输出 800 | 0.04 元 | 4 元 |
| 2.1-pro，输出涨到 8,000（长思考） | 0.25 元 | 25 元 |

5 名学生、不重试，大约是上表的四分之一。预算对这一周的规模很小。认不出手写的风险大于费用。

### 预估批次

排期表里这是 R6 一个 M。实现时可以先提交 mock，再提交火山引擎适配器、脱敏和降级，顺序仍是 R5 之后、R7 之前。不和收卷照片、不和确认页面混在同一个 PR。

2026-11-24 补充：上面几段是当时的设计，句子留在原处。R6 的落法见 ADR 0045。环境变量是 `K12_AI_BASE_URL`、`K12_AI_MODEL`、`K12_AI_API_KEY`。适配器用仓库里已钉死的 httpx，不是新包，也不是当时写的标准库 HTTP。不建 `student_token`。不把模型读回的学号原文存下来。发给第三方的文字里不放 `student-N`。拍板记录第 8 条的原句不改。

## 4. 部署工件

目标：机构老师在这台笔记本的浏览器打开 `https://` 地址，走完闭环。

| 工件 | 现状 | 动作 |
| --- | --- | --- |
| `docker/compose.yml` | 已有。只有 `postgres:16`，没有应用，没有 nginx | 新建试用 compose：Postgres + 应用 + nginx。不把现文件里的本机口令原样拿去试用 |
| 应用镜像 | 仓库无 Dockerfile | 新建。进程仍是现在的 uvicorn 模块 |
| nginx 与 HTTPS | 无 nginx 配置。`scripts/check.conf` 是检查项配置，不是 nginx。#28 仍 OPEN | 新建本机自签或局域网名。不把 #28 标成已完成 |
| 首次管理员 | 已有 `bootstrap_admin.py` 与 `K12_BOOTSTRAP_ADMIN_USERNAME` / `PASSWORD`（`.env.example:56-58`） | 启动脚本复用。口令只在首启环境里，不进仓库 |
| 环境变量模板 | `.env.example` 是开发模板。第 18 行仍写规范化表未建。没有 `K12_AI_PROVIDER`、`K12_VOLCENGINE_API_KEY`、`K12_VOLCENGINE_MODEL` | 新建部署模板，不在本批改 `.env.example`。密钥空着，由操作者本机填 |
| 备份 | `scripts/drill_backup.py` 只演练临时夹具文件，不连库。`scripts/drill_joint_restore.py` 拒绝库名 `k12`、`postgres`、`k12_m11_src`、`k12_m11_dst`，把草稿库和两个文件恢复到空库 | 新建操作脚本：`pg_dump` 加 `K12_FILE_DIR` 打成 7z 并加口令。演练方法沿用 joint restore 的「新空库 + 新目录」，不在已有 `k12` 上 migrate down。#35 仍 OPEN，7z 不代替该 issue 的完成 |
| 恢复演练 | joint restore 已在 M-11 演练过草稿库 | 试用前对新建脚本再跑一次，目标仍是空库 |
| 运维 runbook | 无 | 新建短页：建账号、改口令、看标准输出和 `K12_LOG_DIR`、拉备份、恢复到空目录。不接 Sentry |

`K12_ENV=production` 时连接串或 `K12_FILE_DIR` 为空会退出（`.env.example:12-13`）。试用 compose 必须同时给这两项。CORS 沿用 ADR 0040：production 空列表或 `*` 都拒绝。

## 5. 隐私合规缺口

### ADR 0041 建议正文（本批不写 ADR 文件）

现有 ADR 编号到 `docs/adr/0040-cors-origins.md`。下一号是 0041。建议标题：整页照片、卷面匿名和多模态 Vision。

建议决定：

1. 出卷 PDF 只印学号和页码，不印姓名，不印班级。
2. 收卷是整页照片。服务端一次 Vision 调用同时识别学号、作答和建议。不另加 OCR 组件。
3. 学号脱敏后才传第三方 Vision。题文和提示词里的真学号先换成 `student-N`。照片上印着的学号随图片出站，返回后、进入 API 之前再换成 `student-N`。真学号只存放在 `students.external_id`。
4. 照片文件只允许当堂老师和超级管理员读取，每次成功读取写审计，审计正文不放照片、不放学号、不放姓名。
5. 老师确认后第 N 天，照片压缩加密归档，在线库和 `K12_FILE_DIR` 中的该照片物理删除。题目、发布记录和其他学生的卷保留。
6. Vision 失败不产生正式结论。老师可以手填学号并手评。
7. 机构书面同意第三方传输。在该同意按仓库规则记下之前，`K12_AI_PROVIDER` 不得在载有真实卷面的进程上设为 `volcengine`。

### R6 与「整页」

`RULES.md` 里没有「禁止整页」。交接句是第 83 行：「R1 到 R6 只在服务端用例里执行。AI 建议不是老师结论。旧卷保存发卷时的版本。」

`ARCHITECTURE.md:29` 的 R6 是：「学习记录按老师负责的学科和学生授权。」违反时未授权请求拒绝。这不是照片条款。

整页条款在 ADR 0011 第 34 行的表：「姓名遮挡：默认只传题目区域。整页和去不掉的手写姓名留在机构内，转老师处理。」

建议只写进 ADR 0041，不在本批改 RULES 或 ADR 0011 正文。若以后要改 ADR 0011 那一格，建议文本是：「试用按 ADR 0041。卷面不印姓名。整页照片可以在学号已从题文中脱敏之后，随同一次 Vision 调用交给已书面同意的火山引擎。API 与日志仍不出现真学号和姓名。手写姓名若出现在照片上，由老师决定是否重拍，系统不把该页自动当成答错。」

建议在 `RULES.md` 交接句后另加一句（同样留到 ADR 批次，本批不改文件）：「整页照片按 ADR 0041。题文中的学号脱敏后才传第三方 Vision。」

### purpose 冲突（须拍板）

输入写的是照片 `files.purpose='page'`。代码里 `pg_files.py:16` 已经把出卷 PDF 写成 `purpose='page'`。`publication.py:135-138` 拒绝把这种文件挂到发布资产上。

两条落地途径：

| 途径 | 做法 |
| --- | --- |
| 甲 | 照片继续叫 `page`。先把现有 PDF 改成别的 purpose，并保持「照片不能挂进 publication_asset」 |
| 乙 | PDF 继续叫 `page`。照片用新值 `intake`。权限、审计、归档按输入执行，只是 purpose 字符串不同 |

本调研把乙当作推荐，因为少迁已有 PDF 行。输入的字面值是甲。实现前要选定一个，不能两个字节类型共用一个 purpose 又靠人工分辨。

### 归档天数

ADR 0020 决定不发明保留天数，删除前要人确认并且先有备份。AC-10 不写天数。本试用需要一个 N，否则「确认后归档」无法执行。

推荐 N=7：与这一周试用同长，老师在确认后的一周内仍能在线看照片，满 7 天再归档。这是试用建议，不是替 ADR 0020 填上 DEC。采纳 N=7 时，用 ADR 0041 写下这个试用数字，并写明它不改 ADR 0020 的一般决定。

归档脚本：新建，不放进默认 `scripts/check`。步骤是先跑第 4 节的加密备份，校验备份，再删除已满 N 天且已确认的照片行和文件。删除前打印将删的文件数量，不打印学号。失败则不删。

## 6. M-14 / #47 试用期简化

#47 保持 OPEN。不接 Sentry。

试用期的完成线，按本次输入放宽为三条：

1. 发送端已有端到端行为：URL 为空不发送；URL 非空时 POST 五个字段；失败只打 `webhook_failed`。代码已在 `error_ring.py`。
2. 载荷没有密钥、学号、姓名、照片、请求体。五个字段已满足。补一条测试或证据页，证明序列化结果只有这五键。
3. runbook 写明：操作者每天看标准输出和 `K12_LOG_DIR`。`K12_ERROR_WEBHOOK_URL` 留空，规格允许。

不等真实接收方。规模上来再接 Sentry，并另开完成 #47 的批次。本试用不把 #47 标成完成，也不把 M-14 写成 PASS。

## 7. 阻塞分级

### A. 没有就试不了

| 编号 | 事项 | 批次量级 | 依赖 | 文件 |
| --- | --- | --- | --- | --- |
| A0 | 按 1b 改 README、英文 README、矩阵 | XS | 无 | 三份文档 |
| A1 | 接受 ADR 0041，并记下书面同意，使 A-09 不再挡住真实调用 | S | A0 | 新 ADR。不填 DEC-01、02、04、05、06 |
| A2 | `students.external_id`，API 只返回 `student-N` | S | A1 的字段约定 | 新迁移，`students.py`，`routes_admin.py`，`routes_session.py` |
| A3 | 真实题目进入库，老师能逐题核准 | S | 无代码依赖；内容来自已有草稿契约 | 导入脚本或一条管理路由，`teacher_page.jsx`，`paper_loop.js` |
| A4 | 多题出卷和多题 PDF，只印学号与页码 | M | A2、A3 | `routes_practice.py`，`compose_multi.py` 的 HTTP 接线，`render_paper.py`，`pdf_page.py` |
| A5 | 整页照片上传、读取权限、读取审计 | M | A1、A4，以及 purpose 拍板 | 新用例，`routes_practice.py`，files 适配器 |
| A6 | Vision 端口、mock、火山引擎、题文脱敏、失败不挡确认 | M | A1、A2、A5 | `backend/ai/application/`，practice 确认前的读取 |
| A7 | 老师确认建议，或手填学号后手评 | S | A6 | `confirm_attempt.py`，`teacher_page.jsx` |
| A8 | 从已确认记录再出一份练习 | S | A4、A7 | 老师页再出卷，复用出卷用例 |
| A9 | 单机 Docker、HTTPS、部署环境模板、可执行备份 | M | A6 的变量名要写进模板 | `docker/`、新 Dockerfile、nginx、新备份脚本、runbook |
| A10 | 满 N 天归档并物理删除在线照片 | S | A1 的 N、A5、A9 的备份 | 新归档脚本 |

### B. 有更好，没有也能上课

知识点 PostgreSQL、按知识点检索、同类题推荐、资产字节上传、`figure_geometry`、发布列表改成生成顺序、#82 的 OpenAPI `info.version`、#73 的 httpx2、把 #47 接到真实接收方、补齐 `.env.example:18` 和 `ARCHITECTURE.md:47`（若 R0 不收它们）。

### C. 试用后再做

analysis 切片、delivery 切片、安卓、Tauri、家长端、向量库、高可用、Sentry、密钥轮换、把 #28 和 #35 按原 issue 全文关闭、100 / 300 人规模、DEC-01、DEC-02、DEC-04、DEC-05、DEC-06。

## 8. 批次排布

A 序列没有循环。每一批只依赖更早的批次。

| 批次 | 量级 | 主题 | 依赖 |
| --- | --- | --- | --- |
| R0 | XS，1 PR | 已完成（PR #83）。按第 1b 节改 `README.md`、`README.en.md`、`docs/implementation-matrix.md`，并入库本路线图 | 无 |
| R1 | S | 本批。ADR 0041 成文并接受；DEC-03 记下机构同意；放行条款只追加修订说明。试用归档 30 天见拍板记录第 2 条 | R0 |
| R2 | S | `students.external_id`。已授权老师和管理员的响应和页面可带学号；URL、日志、审计、webhook 与第三方文字不用学号 | R1 |
| R3 | S | 真实题目导入和逐题核准页 | R0。与 R2 无代码交叉，序列上放在 R2 之后，避免同时改老师页 |
| R4 | M | 多题出卷与 PDF。卷面加上二维码、定位标记和固定答题框。`K12_PAPER_QR` 可开关，每张卷记录出卷时是否印码 | R2、R3 |
| R4b | M | 卷面印完整题干和选项。字体由部署环境提供，缺字体显式报错。版式为每页 4 槽位 | R4 |
| R4c | S–M | 已完成。整书导入：书和页命名空间、答案配对、`POST /api/admin/catalog/books/{book_id}/import`、`scripts/import_book.py`。旧路由已删除。已有不带命名空间的行不改写 | R3、R4b |
| R4d | M | 已完成。按题型高度排版（`layout_kind=flow`）。答题区大小属于题目，导入时按题型默认，书清单 `answer_space` 可逐题覆盖。版式参数在 practice 的 JSON 文件，可用 `K12_PAPER_LAYOUT_PATH` 换一份。出卷把每个答题框写入 `practice_item_box`。一整页放不下返回 `item_too_long`，不截断。旧卷 `slots_per_page` 为 1 或 4 不重排。迁移 V013 | R4c |
| R5 | M | 已完成。整页拍照收卷。浏览器用 jsQR 读码，上传前缩小并重新编码成 JPEG。服务端核对卷号、页码、出卷老师，保存 purpose=`intake`。迁移 V014 建 `intake_page`。按题裁切不做 | R1、R4、R4b、R4d |
| R6 | M | 已完成。两步识别、本机判分、脱敏、失败降级。迁移 V015 建 `ai_run` 与 `ai_suggestion`。默认 mock。选择题和纯数字或纯字母的填空不发给模型。学号和页码只存比对结果。见 ADR 0045 | R1、R2、R5 |
| R4e | M | 已完成。新导入的题把文字和公式分开存（V016，不回填旧行）。卷面按排版印出分数、乘方、下标、绝对值、括号、× ÷ ± 和角度。不支持的命令导入记警告，出卷整份拒绝，不印 LaTeX 源码。见 ADR 0046 | R4d |
| R7 | S | 已完成。按卷按题记下老师结论（V017，`teacher_decision`）。采用、改判或手评。AI 建议在老师采用或改判前不是结论。一次采用高把握须老师确认。production 下旧确认路由返回 410。见 ADR 0047 | R6 |
| R4f | M | 已完成。题目册、答案册、目录分开放。页码按册唯一。目录解析成章、节、课时，题目按页码归课。新导入的答案正文带上小问。`\textcircled` 排成圆圈序号。本机 production 试用库不加载合成夹具。迁移 V018。见 ADR 0048 | R4c、R4e |
| 核对页答案页改进 | S | 已完成。在 wisdom-km/md-json-review 做，PR #19 已合入。认「1. 选择题」式标题，拆同一行的多个答案，记下每条答案的课时。题库按课时自动配对答案仍未做 | R4f |
| R6b | S | 已完成。管理后台 `/admin` 拖入或选择书文件夹，调用三个目录的书清单和同一条导入接口，页面上显示报告。先预演，再确认写入。规则不进网页 | R4f |
| R6a | S | 识别率测量。用老师结论和 `ai_suggestion` 对账，测识别率，并定 `K12_AI_REVIEW_THRESHOLD`。接上火山引擎之后、正式试用之前，用 20–50 页真实样张 | R7 |
| R8 | S | 再出一份练习 | R4、R7 |
| R9 | M | Docker、nginx、HTTPS、环境模板、备份脚本、runbook | R6 的变量名 |
| R10 | S | N 天归档 | R1、R5、R9 |
| R11 | S | 试用包：空库演练备份恢复、冒烟、操作录屏 | R6a、R8、R9、R10 |

R0 插在 R1 之前：后面的 PR 正文要引用「表已建、HTTP 仍一题、#66 已关闭」。若正文仍按 README 第 72 行写「表未建」，评审会按过时句子验收。R0 已由 PR #83 合入。R1 是本批。

共 18 批（R0–R11，另有 R4b、R4c、R4d、R4e、R6a、R6b）。粗估工时：R0 2 小时，R1 4，R2 6，R3 8，R4 12，R4b 8，R4c 6，R4d 8，R4e 8，R5 10，R6 12，R6a 6，R6b 4，R7 6，R8 6，R9 12，R10 4，R11 6。合计 128 小时。R0–R4 已完成 32 小时，加上 R4b 的 8 小时、R4c 的 6 小时、R4d 的 8 小时和 R5 的 10 小时，已完成 64 小时，剩余 64 小时。没有历史计时，数字只用于排期。S 按约 4–8 小时，M 按约 8–12 小时。R4d 取 8，与 R4b 相同。R4e 取 8。R6b 取 4，与 R10 相同。R5 取 10。R6 取 12。R6 完成后已完成 76 小时，剩余 52 小时。批次数仍是 18，合计仍是 128 小时。

R4c 已完成。题目键和答案键在写入前加上书号和页码，例如 `rj-math-7a.p0012:1:1`。整本规则在 `POST /api/admin/catalog/books/{book_id}/import`。`scripts/import_book.py` 只读目录、登录、调用接口、写报告。旧路由 `POST /api/admin/catalog/drafts` 已删除。已有不带命名空间的行不改写。核对页保持不连题库、不连数据库。三个存储不共享事务：核准快照写上之后，再导入同一本书是 kept。公式排版见 R4e，上传页见 R6b。

R4d 已在本批完成。新卷 `layout_kind` 为 `flow`，按题型高度排版。答题区大小在导入时按题型默认，书清单 `answer_space` 可逐题覆盖。出卷把每个框写入 `practice_item_box`。版式参数文件可用 `K12_PAPER_LAYOUT_PATH` 替换。旧卷不重排。一整页放不下返回 `item_too_long`。按题裁切不在 R5，留到规模化之前的单独事项，坐标仍读 `practice_item_box`。

R5 已在本批完成。收卷照片 purpose 为 `intake`。二维码在浏览器里用 jsQR 读，上传前缩小并重新编码成 JPEG。服务端核对卷号、页码和出卷老师。无码或读不出时老师手选。迁移 V014。

R6 已在本批完成。识别分转写和判断两步。选择题，以及填空里纯数字或纯字母的空，在本机比对。计算题、解答题和本机判不了的填空才把题干、标准答案和转写结果发给模型。建议不进确认表。失败不挡老师确认。每日上限默认 500。学号和页码只存一致、不一致或没读到。按题裁切仍未做。采用、修改、驳回是 R7。识别率测量是 R6a。

R4e 已在本批完成。新导入的题在快照里分开保存文字和公式。出卷把排好的字形和分数线冻进 `practice_item.formula_draw`。不支持的写法不印源码。旧题和旧卷不改写。根号和方程组大括号未做。

R7 已在本批完成。老师按题采用、改判或手评，写入 `teacher_decision`。AI 建议在采用或改判之前不是正式结论。一次采用高把握须老师点确认。照片被替换后，旧建议不能采用。production 下旧确认路由返回 410，出卷不再绑定合成作答。识别率测量改为 R6a，用老师结论和 `ai_suggestion` 对账。

## 9. 风险

技术：默认 `detail=high` 会把大图缩到 1280 token，方舟说明写了小字可能无法识别。整页手写是否认得出来，本批不能判定，需要真实样张。火山引擎超时、模型 ID 填错、Base64 超过 10 MB，都会走降级。笔记本上的 Postgres + 应用 + nginx 未测过内存占用。`docker/compose.yml` 写的是 `postgres:16`，本机已有容器可能是别的主版本，试用镜像要单独定，不沿用未核对的标签。

隐私：ADR 0041 未接受就跑真实照片，会和 ADR 0011 第 34 行、A-09 冲突。purpose 未拍板就会把照片和 PDF 写进同一个 `page`。日志若带上学号，违反 L-05。

运维：操作备份脚本还不存在。joint restore 证明的是草稿库，不是这台笔记本上的试用库。老师页已有收卷区。真实题列表仍可能让老师不好用。

费用：按第 3 节，100 次调用大约 0.5 元到 25 元，取决于模型和思考长度。不是采购决定。

法律：输入写明机构已书面同意第三方传输。仓库里 DEC-03 仍空，A-09 仍禁止未确认就把学生卷发给真实模型。同意书本身是否覆盖学号出现在照片里、保留期限和删除，本批看不到同意书原文，不能判定条款已经齐。

2026-11-24 补充：上一句「DEC-03 仍空」是写路线图时的状态，留在原处。DEC-03 现已有同意记录。真实调用仍按 A-09 和 ADR 0045。费用一句里的 0.5 元到 25 元是第 3 节当时的估算，不是 R6 的实测账单。R6 没有跑计费调用。公开价目和日期见 `docs/ops/ai.md`。

## 10. 推荐开始顺序和试用日

R0–R4、R4b、R4c、R4d、R5、R6 已合入。R4e 由本批完成。下一代码批是 R6a，排在接上真实模型之后。按题裁切不在本批。R6b 不挡试用，导书频繁时可以提前做。

下面这一段是 R6 完成后、R4e 开始前的数字，留在原处。工时按第 8 节 18 批、128 小时。当时已完成 76 小时，剩余 52 小时。2026-11-24（周二）用于 R4b、R4c、R4d、R5 与 R6。剩余从 2026-11-25（周三）起算，每个工作日 6 小时，周末休息，不另扣节日。12 月 25 日是星期五，按工作日计。

上一档乐观约 24 小时含本批 R6 的 12 小时。R6 完成后乐观剩余约 12 小时。

| 档 | 假设 | 日期 |
| --- | --- | --- |
| 乐观 | 公式一次过，样张第一次就能认，方舟一次接上。约 12 小时，2 个工作日：11 月 25、26 日 | 2026-11-26 |
| 现实 | 剩余 52 小时，9 个工作日。第 1 天是 2026-11-25，第 9 天是 2026-12-07 | 2026-12-07 |
| 悲观 | 在现实档的 9 天之上，识别率不够再做一轮样张和提示词（5 个工作日），方舟接入踩坑（3 个工作日），评审延后（5 个工作日）。合计 22 个工作日。12 月 25 日计入，但第 22 天在它之前。第 22 天是 2026-12-24 | 2026-12-24 |

### 2026-11-24 R4e 完成后

R4e 的 8 小时计入已完成。批次数仍是 18，合计仍是 128 小时。已完成 84 小时，剩余 44 小时。上一张表是 R6 完成后的排期。起算日、每日 6 小时、周末休息、12 月 25 日按工作日，这些规则不变。

上一档乐观约 12 小时，其中公式这一段按 8 小时计，已经做完。乐观剩余约 4 小时。

| 档 | 假设 | 日期 |
| --- | --- | --- |
| 乐观 | 样张第一次就能认，方舟一次接上。约 4 小时，1 个工作日：11 月 25 日 | 2026-11-25 |
| 现实 | 剩余 44 小时，8 个工作日。第 1 天是 2026-11-25，第 8 天是 2026-12-04 | 2026-12-04 |
| 悲观 | 在现实档的 8 天之上，识别率不够再做一轮样张和提示词（5 个工作日），方舟接入踩坑（3 个工作日），评审延后（5 个工作日）。合计 21 个工作日。第 21 天是 2026-12-23 | 2026-12-23 |

### 2026-11-25 R7 完成后

R7 的 6 小时计入已完成。批次数仍是 18，合计仍是 128 小时。已完成 90 小时，剩余 38 小时。上一张表是 R4e 完成后的排期。剩余从 2026-11-26（周四）起算。每日 6 小时、周末休息、12 月 25 日按工作日，这些规则不变。下一代码批是 R6a。

上一档乐观约 4 小时已经做完。本批是 6 小时。乐观剩余按下一代码批一次过计，1 个工作日。

| 档 | 假设 | 日期 |
| --- | --- | --- |
| 乐观 | 样张第一次就能认，方舟一次接上。约 6 小时，1 个工作日：11 月 26 日 | 2026-11-26 |
| 现实 | 剩余 38 小时，7 个工作日。第 1 天是 2026-11-26，第 7 天是 2026-12-04 | 2026-12-04 |
| 悲观 | 在现实档的 7 天之上，识别率不够再做一轮样张和提示词（5 个工作日），方舟接入踩坑（3 个工作日），评审延后（5 个工作日）。合计 20 个工作日。12 月 25 日计入，但第 20 天在它之前。第 20 天是 2026-12-23 | 2026-12-23 |

### 2026-11-25 R4f 完成后

R4f 的 8 小时计入已完成。另插入「核对页答案页改进」6 小时，在另一个仓库做，尚未开始。批次数改为 20，合计改为 142 小时。已完成 98 小时，剩余 44 小时。上一张表是 R7 完成后的排期。剩余从 2026-11-26（周四）起算。每日 6 小时、周末休息、12 月 25 日按工作日，这些规则不变。

本仓库的下一批代码是 R6b，排在核对页答案页改进之后、R6a 之前，复用三个目录的书清单。核对页那一批不在本仓库。

上一档乐观约 6 小时已经做完。乐观剩余按下一代码批 R6b 一次过计，4 小时，1 个工作日。下表三个日期不变。

| 档 | 假设 | 日期 |
| --- | --- | --- |
| 乐观 | 样张第一次就能认，方舟一次接上。约 4 小时，1 个工作日：11 月 26 日 | 2026-11-26 |
| 现实 | 剩余 44 小时，8 个工作日。第 1 天是 2026-11-26，第 8 天是 2026-12-07 | 2026-12-07 |
| 悲观 | 在现实档的 8 天之上，识别率不够再做一轮样张和提示词（5 个工作日），方舟接入踩坑（3 个工作日），评审延后（5 个工作日）。合计 21 个工作日。12 月 25 日计入，但第 21 天在它之前。第 21 天是 2026-12-24 | 2026-12-24 |

### 2026-11-25 R6b 完成后

核对页答案页改进的 6 小时已在 wisdom-km/md-json-review PR #19 完成。R6b 的 4 小时计入已完成。批次数仍是 20，合计仍是 142 小时。已完成 108 小时，剩余 34 小时。上一张表是 R4f 完成后的排期。剩余从 2026-11-26（周四）起算。每日 6 小时、周末休息、12 月 25 日按工作日，这些规则不变。

本仓库的下一批代码是 R6a。

上一档乐观约 4 小时已经做完。核对页 6 小时和本批 4 小时已经做完。乐观剩余按下一代码批 R6a 一次过计，6 小时，1 个工作日。

| 档 | 假设 | 日期 |
| --- | --- | --- |
| 乐观 | 样张第一次就能认，方舟一次接上。约 6 小时，1 个工作日：11 月 26 日 | 2026-11-26 |
| 现实 | 剩余 34 小时，6 个工作日。第 1 天是 2026-11-26，第 6 天是 2026-12-03 | 2026-12-03 |
| 悲观 | 在现实档的 6 天之上，识别率不够再做一轮样张和提示词（5 个工作日），方舟接入踩坑（3 个工作日），评审延后（5 个工作日）。合计 19 个工作日。12 月 25 日计入，但第 19 天在它之前。第 19 天是 2026-12-22 | 2026-12-22 |

### 本批不能判定

Vision 对真实整页手写的识别率。一张 A4 在 Token 计算器里的精确 token（上表用的是文档公式和封顶，不是样张）。同意书是否覆盖照片中的学号。笔记本 Docker 的内存是否够。N=7 是否被机构接受。purpose 用甲还是乙。

## 请拍板的三项

1. 照片 purpose 用甲（继续叫 `page`，并迁走 PDF）还是乙（照片叫 `intake`）。
2. 试用 N 是否采用 7。ADR 0020 目前不写天数。
3. 第一版模型用 doubao-seed-2.0-lite 的 `xhigh`，还是 2.1-pro。以及书面同意记入 DEC-03，还是记入 ADR 0041 的接受记录。不记下之前，真实调用仍被 A-09 挡住。

#28 用本机自签证书、#35 用 7z 口令，都只覆盖这一次试用，两个 issue 保持打开。若这点不接受，R9 的范围要加大，悲观日期再往后。

## 2026-11-23 拍板记录

1. 照片 purpose 用 intake，不沿用 page；现有 PDF 的 page 不迁移。publication_asset 的守卫在收卷批次加一条：拒绝 files.purpose='intake'。
2. 照片归档天数：试用期 30 天，由 K12_INTAKE_RETENTION_DAYS 配置，ADR 0041 写明规模化后再评估缩短。
3. 第一版模型 doubao-seed-2.1-pro，由 K12_AI_MODEL 配置，不开长思考；detail 取值在接 Vision 的批次用真实样张定。机构书面同意记入 DEC-03，ADR 0041 引用 DEC-03；同意的事实（日期、签署方、范围）由用户在 R1 提供，本批不写。
4. 卷面加二维码和定位标记，K12_PAPER_QR 可开关，每张卷记录是否印码，试用做 A/B 对比。
5. 定位按"卷 + 页"：有码扫码；无码老师选批次 + 多模态认学号页码；都失败老师手选。
6. 多模态识别分转写、判断两步，有看不清标记和置信度；后续准确率路线按图片质量 → 模型调优 → 第二识别引擎 → 人在环逐层推进。
7. 接火山引擎之后、正式试用之前，新增一批"识别率测量"（20–50 页真实样张）。
8. 学号（`external_id`）可以出现在有授权的老师和管理员调用的 API 响应和页面里。学号不得出现在 URL 路径、日志、审计 `detail_json`、错误上报 webhook 正文、发给第三方模型的文字内容，以及没有授权的老师能拿到的任何响应。URL、日志、审计、跨切片引用一律用内部学生 ID。`student-N` 这类临时序号只用于发给第三方的文字内容（如果需要指代学生），不作为界面上的主要标识。此前「所有 API 响应只用 `student-N`」的说法作废。
9. 卷面印完整题干和选项。字体由部署环境提供，缺字体显式报错。版式为每页 4 槽位。
10. 真题导入的推送步骤放在题库这边（`scripts/import_book.py`）。核对页 md-json-review 保持不连题库、不连数据库。
11. 答题区大小属于题目。导入时按题型给默认值，可在书清单里逐题覆盖。排版自动取用。老师出卷时不调。出卷时把每个答题框的实际坐标存进卷记录。
12. 公式按排版后的样子印在卷面（分数上下排、乘方上标、绝对值、× ÷ ±），不印 LaTeX 源码。必须在试用之前完成。

## 2026-11-24 补充（R4d）

新卷不再使用每页 4 个等高槽位。版式类型是 `flow`：按题目高度从上往下排，答题框坐标写入 `practice_item_box`。第 9 条是 R4b 当时的决定，原文不改。`slots_per_page` 为 1 或 4 的已发出卷仍按那一版打开。

## 2026-11-24 补充（R5）

二维码在浏览器里读，用 jsQR；服务端核对卷号、页码、出卷老师。上传前在浏览器里缩小并重新编码成 JPEG，去掉拍摄信息。无码或读不出时老师手选。按题裁切仍未做。

## 2026-11-24 补充（R6）

选择题，以及填空里每个空都是纯数字（含负号、小数）或纯字母的，在本机比对，不把标准答案发给模型。计算题、解答题，以及本机判不了的填空，才把题干、标准答案和转写结果发给模型。看不清记不确定，不记为做错。

第 8 条里「`student-N` 只用于发给第三方的文字」原文不改。本批的转写和判断都不在文字里放学号，也不放 `student-N`。照片上印着的学号仍随图片出去，范围以 DEC-03 为准。模型读回的学号只比对，只存一致、不一致或没读到。

第 9 条原文不改。

## 2026-11-25 补充（R7）

R7 提到 R6a 之前。R6a 以老师结论为基准，和 `ai_suggestion` 对账，测识别率，并定 `K12_AI_REVIEW_THRESHOLD`（默认 0.6）。AI 建议在老师采用或改判之前不是正式结论。一次采用高把握也须老师点击并确认。

## 2026-11-25 补充（R4f）

R4f 排在 R6b 与 R6a 之前。题目册、答案册、目录分开放。页码按册唯一。题目按目录上的页码范围归到课时。自动按课时配对答案留给核对页记下每条答案的课时之后。R6b 复用这三个目录的书清单。

核对页答案页改进在 wisdom-km/md-json-review：认「1. 选择题」式标题，拆同一行的多个答案，记下课时。那一批不改本仓库。

## 2026-11-25 补充（R6b）

核对页答案页改进已在 wisdom-km/md-json-review PR #19 合入。本仓库 R6b：管理后台 `/admin` 拖入或选择书文件夹，复用三个目录的书清单和 `POST /api/admin/catalog/books/{book_id}/import`。先预演，预演没有拦截才确认写入。规则留在服务端。下一批是 R6a。按课时自动配对答案仍未做。
