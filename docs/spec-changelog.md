# 规格变更

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-11-14 | 把方案 1.1 落成 PRD、ARCHITECTURE、RULES、ADR 和门禁。未改需求编号。 | 用户指定方案《初中数学题库与教学系统完整需求与架构设计方案》1.1（2026-11-07），并要求按从想法到架构的流程写入本仓库。 |
| 2026-11-14 | 增加 ADR 0011：网页与桌面同一套界面，桌面用安装壳。版本、机型、供应商和备份数字仍不拍板。 | 用户要求项目支持网页和桌面，并按架构流程给尚未确认的框架与部署项一个建议。 |
| 2026-11-14 | 改顺序：第一段只做网页上的核验、出卷和确认。安卓拍照随后。桌面壳等网页在老师电脑上能用再加。不把 Electron 当作退路。第一段只建 catalog 和 practice。 | 用户要求按评审意见改正文档里不合理的顺序。 |
| 2026-11-14 | AGENTS 路由表把第一段网页、安卓拍照、桌面壳分开。执行计划补上计划—实际—证据。 | 用户要求按给 AI 的约束文档继续。 |
| 2026-11-14 | 依赖方向、第一段范围、界面不导入 backend、日志敏感字段，改由检查脚本拒绝。不能机器查的仍标 review。 | 用户要求按架构护栏继续。 |

| 2026-11-14 | 开工门按阶段分开。CI 把「命令已记录」和「文档冒烟」与业务测试分开。相对导入与绝对导入使用同一条边界。M1 补上四项执行契约。DEC-01 到 DEC-06 集中列出，仍不代机构填写。 | 用户要求按评审意见改本地文档和检查。 |
| 2026-11-14 | 采纳 Python 3.12、FastAPI、PostgreSQL、React。`catalog` 和 `practice` 增加合成数据上的出卷与确认骨架。原始方案 1.1 入库。许可证定为 MIT。 | 用户要求按所列顺序改仓库。DEC-01 到 DEC-06 仍不代机构填写。 |
| 2026-11-14 | 发卷快照和操作键写成明确类型。空白版本号和空白操作键拒绝。执行计划记下未核准拒绝、幂等和版本冲突。 | 用户要求做 P1 强化。未安装框架包。 |
| 2026-11-14 | 阶段切片改为 `scripts/check.conf` 的 `PHASE_SLICES`，默认仍是 catalog 和 practice。补充健康检查占位、错误上报字段和合成夹具说明。 | 用户要求做 P2。未安装框架包。M-14 的真实接口仍未落地。 |
| 2026-11-16 | 确认改为一次原子写入。同一复核槽位只留一条正式记录。待确认作答必须绑在该卷、小问和复核版本上。请求里的学科和老师只作为输入，学科以题库记录为准。学生卷状态补上待渲染、可打印、已发放的条件。启动检查改为安装之后限时探测，`SERVICE_CMD` 仍空。 | 用户要求落实评审里的优先修复。未安装框架包。PDF 渲染程序和操作键生成方仍待确认。 |
| 2026-11-16 | 操作键幂等改为卷、小问、服务端老师和键字符串。同一复核槽位仍只留一条。启动探针确认自己拉起的进程树已经退出，业务冒烟有单独超时。`SERVICE_CMD` 仍空。 | 用户要求补上 PR #9 的这两项。未安装框架包。 |
| 2026-11-16 | 本机合成 HTTP 接上核验发布、出卷、单页 PDF、确认和同键重试。内存适配器保留。PostgreSQL 不在这一步。产品 PDF 渲染程序和操作键生成方仍待确认。 | 用户要求做 M1 本机合成网页闭环。实测见 `docs/evidence/m1-web-loop-2026-11-16.md`。 |
| 2026-11-16 | 学生卷 PDF 去掉答案和解析。修订改为新的未核准版本，核准仍绑在精确的题目版本和答案版本上。渲染使用发卷时冻结的公式。样张覆盖 Latin-1（含 `2×3`）；超出该范围时卷留在待渲染并给出稳定原因。出卷和作答绑定同一次写入。列表和正式记录计数按服务端老师过滤。 | 用户要求按 PR #10 的评审修复 M1。产品 PDF 渲染程序仍待确认。实测补在 `docs/evidence/m1-web-loop-2026-11-16.md`。 |
| 2026-11-16 | 并行修订各自得到不同的未核准版本。样张改用 WinAnsi，使受支持字符在查看器里可见。作答按当前复核版本读取，文字来自独立的待确认作答夹具。启动探针核对本次进程已经绑定并活到冒烟结束。 | 用户要求完成 PR #10 的收尾复验。产品 PDF 渲染程序仍待确认。实测补在 `docs/evidence/m1-web-loop-2026-11-16.md`。 |
| 2026-11-16 | 正式发放的晚到响应只更新发起那次的卷面。切卷之后，旧的成功或失败不覆盖当前卷、作答和确认请求。启动探针在同一就绪时限内等待绑定和健康响应，提前退出立即失败。 | 用户要求做 PR #10 合入前的两项定向修复。产品 PDF 渲染程序仍待确认。实测补在 `docs/evidence/m1-web-loop-2026-11-16.md`。 |
| 2026-11-17 | 出卷进行中先关闭旧卷的发放和确认。晚到的发放按当前卷号归属，不把另一张卷的作答拼进确认请求。健康响应的连接和正文读取共用同一个就绪截止时间，超过预算按就绪失败并停掉本次进程。 | 用户要求补 PR #10 里已复现的两项边界。产品 PDF 渲染程序仍待确认。实测补在 `docs/evidence/m1-web-loop-2026-11-16.md`。 |
| 2026-11-17 | 已经确认的发放不会被更旧的列表快照改回可打印。当前打开的卷、作答、确认请求和同键重试仍属于后一张卷。健康探针接受预算内的分块正文，也继续接受 Content-Length；只请求 http，其它协议在连接前拒绝。 | 用户要求补 PR #10 里已复现的列表覆盖和分块健康正文。产品 PDF 渲染程序仍待确认。实测补在 `docs/evidence/m1-web-loop-2026-11-16.md`。 |
| 2026-11-17 | 记下 PR #10 与 PR #9 已合入 main `aa629cd`。第一段代码在 main。名单外许可证仍待决定，不改依赖。 | 用户要求记下这次合入。老师自己的电脑和打印机仍未做。见 `docs/evidence/m1-on-main-2026-11-17.md`。 |
| 2026-11-17 | 核对页的 `k12-question-draft` 由 catalog 解析一次后保存。不另做题目 JSON。PostgreSQL 仍未连接。建表列见 ADR 0013。 | 用户要求核对完的数据直接进入题库，连库时按同一形状建表。 |
| 2026-11-17 | 参考答案补上 ADR 0014。扫描件、模型候选和老师修改共用 `answer_version`，`origin` 区分来源。学生作答不进该表。解析器和迁移仍没有。 | 用户要求答案有对应的表，并审查连库时文档是否够用。 |
| 2026-11-17 | 发布记录、知识点、练习册和多题练习的列写入 ADR 0015。没有行不建表。没有标签的题不进知识点检索。现在仍是一卷一题。 | 用户要求以架构和产品的角度补上文档里还没有的对象，并合并已通过检查的改动。 |
| 2026-11-17 | OCR 答案按 `k12-answer-draft` 第 1 版一份文件一条答案进入内存。`import_answer_draft` 解析一次。确认后仍不能出卷。PostgreSQL 仍不连接，不建表。 | 用户要求扫描答案和题目一样，改完就能对上答案表，不再做中间转换。 |
| 2026-11-17 | 解题方法单独成目录。某一次错因只作建议，并指向已有的知识点和方法。模型不新建目录行。表未建。见 ADR 0016。 | 用户要求按该建议写入项目文档。 |
| 2026-11-17 | 标明第一段计划停在 `aa629cd`。其后的答案导入和 ADR 0016 已在 main。ADR 0012 的第一次写入补上 ADR 0015 和 0016。ADR 0014 写明列已有、表未建。ADR 0015 的表格不再被说明句切开。两个本机服务不要同时占用 8765。 | 用户要求按文档审查建议修改。历史证据和方案 1.1 未改。 |
| 2026-11-17 | 题目草稿和答案草稿先按 JSON Schema 校验形状。不新增包。失败仍是 `not_draft`。见 ADR 0017。 | 用户要求两边生成和导入都通过同一份可执行契约。 |
| 2026-11-17 | 契约文件增加 `version`。草稿文件增加 `schema_version`。解析按 `$id` 和版本分发。未知版本仍是 `not_draft`，说明写出收到的版本。见 ADR 0018。 | 用户要求契约统一，并按版本分发。 |
| 2026-11-18 | README 写明兼容矩阵。标记 `draft-contract-1` 打在包含这张表的 main 上。 | 用户要求契约进入两边 main 之后再标记，避免 tag 指到旧契约。 |
| 2026-11-18 | ADR 索引写上编号、标题、状态和切片。每条 ADR 开头有状态行。 | 用户要求能一眼看出采纳、提议或已被取代。 |
| 2026-11-18 | 端口表、数据模型和日志事件表移到 docs/arch。根上的 ARCHITECTURE 留下链接。日志门禁要查的句子仍留在根上。 | 用户要求根文档留下分层、不变量和禁止项，表拆出去。 |
| 2026-11-18 | 增加六个切片的实现矩阵。PR 模板要求改了实现程度就更新该表。 | 用户要求能一眼看出端口、适配器和测试做到哪一步。 |
| 2026-11-18 | ADR 0019 采纳：不做 SQLite。第二个适配器等到第一次 PostgreSQL 写入。 | 用户选定数据库只用 PostgreSQL。不改 ADR 0012。没有迁移，没有空表。 |
| 2026-11-18 | ADR 0020：学情删除覆盖一名学生的照片、作答记录和建议。不写保留天数。PRD 增加 US-12 和 AC-10。 | 用户要求按建议记下学情怎么留、怎么删。不改 ADR 0008 正文。不填 DEC-01 到 DEC-06。 |
| 2026-11-18 | ADR 0021：真实阶段前，PostgreSQL 适配器、文件存储适配器和真实老师登录要同一次走完 AC-01、AC-02、AC-04。 | 用户要求按建议先记下这次集成验证。不连接 PostgreSQL，不建表。 |
| 2026-11-18 | ADR 0022 提议：Noto Sans CJK 是 SIL Open Font License 1.1，不在允许名单里。需要人工决定。不加入字体，不改合成 PDF。 | 用户要求按建议先确认字体许可证。OFL 不在 MIT、BSD、Apache-2.0 里。 |
| 2026-11-18 | ADR 0023：开发依赖 openapi-typescript 7.13.0（MIT）生成 apps/web/src/api.types.ts。默认进程仍关闭 OpenAPI。 | 用户要求按建议生成类型并让 CI 核对。不打开合成服务的文档地址。 |
| 2026-11-18 | ADR 0025 到 0031：角色和会话、首个管理员、argon2id、内存加 PostgreSQL、迁移、日志双流、react-router。`PHASE_SLICES` 增加 identity。不做 JWT、SSO、密码找回、双因素、自助注册、学生或家长账号、SQLite 过渡。 | 用户要求先写下这些决定。不改 ADR 0008 和 0019 的正文。题目表仍等有行再建。 |
| 2026-11-18 | ADR 0024 采纳：中文用本机楷体，没有则用微软雅黑或黑体。只嵌入这一页的字形。字体文件不进仓库。 | 用户选定楷体或微软黑体。不接受把 OFL 字体放进仓库。不改 ADR 0022 正文。 |
| 2026-11-18 | HTTP 会话 cookie 与 CSRF。出卷老师来自会话，不再写死老师编号。不设置 `K12_PG_DSN` 时不连接。设置后连接并迁移 identity 与审计。psycopg、psycopg-binary、psycopg-pool 的 LGPL-3.0 标为已审。不改 ADR 0012 和 0028 正文。题目表仍不建。 | 用户接受不否决题目表，也不否决连接池包。 |
| 2026-11-18 | 网页路径是 `/login`、`/` 和 `/admin`。写操作带 `X-K12-CSRF`。未登录打开受保护页去 `/login`。出卷老师仍由会话决定。页面测试用 vitest 5.1.1 和 jsdom 29.1.1。 | ADR 0031 已采纳。`react-router-dom` 7.18.5 已预批准。不改 ADR 0031 正文。 |
| 2026-11-18 | 证据页记下本机 PostgreSQL 上的管理员引导、登录、授权、发卷、撤销和按日日志。README 增加登录、管理员后台、PostgreSQL 三行。默认进程仍不连接。本批标记 v0.2.0。 | 用户要求做这一班文档和证据。不改 ADR 正文。已有的 #28、#30、#33、#34、#35 不重复开。 |
| 2026-11-18 | ADR 0032 到 0039：运行模式、会话清理、迁移锁、存活与就绪、首次改口令、读审计、最后一名管理员、catalog 与 practice 落库。README 两处改为 identity 与审计已在 PostgreSQL。AC-01 到 AC-09 的句子不改。表和代码还没写。 | 用户要求 C0 只写决定。不改已有 ADR 正文。0039 不再另写第二条落库 ADR。 |
| 2026-11-18 | `V002__catalog_practice.sql` 建 approvals、papers、paper_pages、attempts、confirmations、files。适配器是 `PgApprovals`、`PgPractice`、`PgFiles`。`K12_PG_DSN` 有值时组合根接上这三件。页字节在 `K12_FILE_DIR`。规范化题目表和答案表仍不建。 | 用户要求做 C1。不另写落库 ADR。实测见 `docs/evidence/catalog-practice-pg-2026-11-18.md`。 |
| 2026-11-18 | `K12_ENV` 区分 development 与 production。`GET /health` 与 `GET /health/live` 仍只表示进程还在。`GET /health/ready` 检查数据库和迁移。同一 IP 每分钟超过 30 次返回 `ip_throttled`。migrate 的一次 up 或 down 在一个事务里持有咨询锁。 | 用户要求做 C2。不改 ADR 0032、0034、0035 正文。 |
| 2026-11-18 | 过期会话先标吊销，满 `K12_SESSION_RETAIN_DAYS`（默认 30）再删。登录尝试按 `K12_LOGIN_ATTEMPT_RETAIN_DAYS`（默认 30）删除。停用、启用、重置口令的成功路径吊销尚未过期的会话。学情天数仍不写。 | 用户要求做 C3。不改 ADR 0033、0020、0030 正文。 |
| 2026-11-18 | 引导管理员带 must_change_password。改口令成功前只允许会话、注销和改口令。读审计写入 admin_read_committed，明细只有 limit、offset 和筛选字段名。disable_user 与 change_role 拒绝最后一名活跃管理员且不写。 | 用户要求做 C4。不改 ADR 0036、0037、0038 正文。 |
| 2026-11-18 | 响应默认带 Content-Security-Policy 和 Permissions-Policy。`K12_SECURITY_HEADERS=0` 关闭这两项。`/account` 可改自己的口令。管理页列出并一次吊销当前用户尚未过期的会话。 | 用户要求做 C5。不改 ADR 0025 正文。 |
| 2026-11-19 | `K12_OPENAPI` 默认 0，为 1 时才打开 `/docs` 和 `/openapi.json`。CI 导出 `apps/web/src/api.openapi.json` 并用 git diff 对账。合成口令改从 `K12_SYNTH_SECRET` 读取。production 不加载合成数据。 | 用户要求做 C6。不改 ADR 0023 正文。 |
| 2026-11-19 | `K12_ERROR_WEBHOOK_URL` 非空时，ErrorRing 异步 POST 五个字段。超时 2 秒，最多重试 1 次。失败只打一条 WARN。外部接收方仍未对接。 | 用户要求做 C7。不改 ADR 0030 正文。不关闭 #47。 |
| 2026-11-19 | `V004__questions_answers.sql` 建 `questions` 和 `answers`。核准时追加一行，不覆盖已有 `question_id`。子表仍不建。 | 用户要求做 D1，并确认版本号、两张表、主键名、`origin` 和时间列。不改 ADR 0013、0014、0039 正文。 |
| 2026-11-20 | `V005__catalog_subtables.sql` 建 `question_option`、`sub_question`、`question_asset`、`answer_part`、`answer_asset`。核准带真实题型时写子行，不再写 `unresolved`。`figure_geometry` 和 `answer_decision` 仍不建。 | 用户确认父键、行标识、`position`、jsonb、可空题型和 `sub_key`。不改 ADR 0013、0014、0039 正文。 |
| 2026-11-20 | knowledge 切片增加端口和内存适配器。挂标签检查已核准题目、主知识点和学科。不建表，不写 V006。 | 用户要求按 ADR 0015 和 0016 起内存目录，并补上学科一致与不提供摘标签。不改 ADR 正文。 |

| 2026-11-24 | 删除 `POST /api/admin/catalog/drafts`。新增 `POST /api/admin/catalog/books/{book_id}/import`。整书规则、书和页命名空间、答案配对都在这条路由。见 ADR 0042。 | 用户要求整书导入。不改契约文件。不改已有题目、答案、核准行。 |
| 2026-11-24 | 书清单和核准行增加 `answer_space`。只改答题区大小的重导记 `space_changed`。新卷按高度排版。一整页放不下返回 `item_too_long`。版式参数不合法时，production 启动失败，development 出卷返回 `layout_invalid`。见 ADR 0043。 | 用户要求按题型排版，坐标存进卷记录。不回填已有行。不改已发出的卷。 |
| 2026-11-24 | 新增 `PUT /api/practice/papers/{paper_id}/pages/{page_no}/intake`、`GET /api/practice/papers/{paper_id}/intake`、`GET /api/practice/intake/{intake_id}/image`。错误码：`permission_denied` 403、`csrf` 403、`unauthenticated` 401、`paper_not_found` 404、`not_found` 404、`file_missing` 404、`page_out_of_range` 400、`not_image` 400、`validation_failed` 400、`too_large` 413、`qr_mismatch` 409、`page_already_received` 409、`file_purpose_conflict` 409。`publication_asset` 对 purpose 为 intake 的文件返回 `intake_file_rejected`。见 ADR 0041 修订与 ADR 0044。 | 用户要求整页拍照收卷。浏览器读码，服务端核对。不改已有 files 行，不改已发出的卷。 |
| 2026-11-24 | 新增 `POST /api/practice/intake/{intake_id}/ai-runs`（202，正文 `run_id` 与 `status`）和 `GET /api/practice/ai-runs/{run_id}`。开始一次识别的 HTTP 错误：`ai_run_in_progress` 409、`ai_daily_limit` 429，以及已有的 `permission_denied` 403、`csrf` 403、`unauthenticated` 401、`not_found` 404。运行失败写在 `ai_run.status=failed` 上，错误码是 `timeout`、`auth_failed`、`model_output_invalid`、`network`、`interrupted`、`model_not_found`、`ai_provider_incomplete`、`failed`。这些码不是开始请求的 HTTP 状态。见 ADR 0045。 | 用户要求两步识别、本机判分、脱敏和失败降级。建议不写入确认表。不改出卷、版式、收卷和导入。 |
| 2026-11-24 | 目录项增加 `formula_note`。旧核准行是「公式未结构化」。出卷错误码：`formula_unsupported` 409、`formula_unstructured` 409、`formula_too_wide` 409。整书导入对不支持的命令记同名警告，不挡导入。见 ADR 0046。 | 用户要求卷面按排版印公式，不印 LaTeX 源码。不回填旧行。不改已发出的卷。不改契约文件。 |
| 2026-11-25 | 新增 `GET /api/practice/papers/{paper_id}/review`、`PUT /api/practice/papers/{paper_id}/items/{order_no}/decision`、`POST /api/practice/papers/{paper_id}/decisions/adopt-confident`。写操作错误码：`cannot_adopt_unsure` 409、`suggestion_stale` 409、`suggestion_required` 409、`invalid_action` 409、`invalid_verdict` 409、`note_too_long` 409、`store_failed` 409，以及已有的 `permission_denied` 403、`csrf` 403、`not_found` 404。production 下 `POST /api/practice/confirmations` 返回 `confirmations_retired` 410。见 ADR 0047。 | 用户要求老师结论成为正式结论。不改写已有确认行。不改已发出的卷。 |
| 2026-11-25 | 书清单增加 `question_dir`、`answer_dir`、`toc_dir`、`toc_page_offset`。页码按册唯一。新错误码在整书报告里：`answer_page_not_marked`、`unpaired_answer`。目录认不出的行是 `toc_unparsed_line`，不挡导入。重导目录变化记 `toc_changed`。新增 `GET /api/catalog/books/{book_id}/lessons`，没有这本书是 `not_found` 404。`\textcircled` 超出 1 到 20 仍是出卷 `formula_unsupported` 409。见 ADR 0048。 | 用户要求三份真书目录能导入，并按课时选题。不回填已有核准行。不改已发出的卷。不改契约文件。 |
| 2026-11-25 | 新增 `GET /api/admin/ai/accuracy`。查询参数 `provider`、`model` 可省略。没有新错误码。未登录仍是 `unauthenticated` 401，老师仍是 `permission_denied` 403。成功读取不写审计。见 ADR 0045 修订（R6a）。 | 用户要求对账报表和阈值测算。不改 `K12_AI_REVIEW_THRESHOLD` 的默认值。不改识别、批改、收卷、出卷和导入。不新增迁移。真实样张实测仍未做。 |
| 2026-11-25 | 新增 `POST /api/practice/papers/{paper_id}/follow-up`。可选 `order_nos`、`review_version_id`。省略题号时只再出当前结论为 `incorrect`、`partial`、`blank` 的题。新错误码：`invalid_order_no` 409、`decision_required` 409、`no_retry_items` 409。原卷不存在是 `not_found` 404。不是出卷老师或授权已撤销是 `permission_denied` 403。停用仍是 `retired` 409。V019 给 `papers` 增加可空 `source_paper_id`，无外键、不回填。见 ADR 0049。 | 用户要求批改确认后给该学生再出一份巩固练习。不依据未采用的 AI 建议。不改原卷、快照、照片、建议和老师结论。不按知识点推荐新题。 |

| 2026-11-25 | 试用部署包：`docker/Dockerfile`、`docker/compose.trial.yml`、`docker/nginx.conf`、`.env.trial.example`、`scripts/make_trial_cert.py`、`scripts/backup_trial.py`、`scripts/restore_trial.py`。没有新的 HTTP 路由，没有新的错误码，没有新迁移。见 ADR 0050。 | 用户要求单机试用可以容器化，并用 HTTPS 和联合加密备份迁到云主机之前先跑起来。`#28` 与 `#35` 仍打开。 |
| 2026-11-27 | 读取已归档收卷照片 `GET /api/practice/intake/{intake_id}/image`，以及对其发起 `POST /api/practice/intake/{intake_id}/ai-runs`，返回 `intake_archived` 410。批改页和 `GET /api/admin/ai/accuracy` 没有新错误码。V020 给 `intake_page` 增加可空的 `archived_at`，无外键、不回填。见 ADR 0041 修订（R10）。 | 用户要求满 N 天先加密归档并核对 SHA-256，再删除在线照片字节。不删出卷 PDF，不删老师结论、识别建议和出卷记录。 |

DEC-03 已有同意记录。DEC-01、02、04、05、06 仍待机构确认。
