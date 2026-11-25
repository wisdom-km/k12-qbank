# ADR 索引

状态只用三个词：`proposed`、`accepted`、`superseded`。每条 ADR 开头有同样的状态行。正文里的日期和原句不改。

没有整条被取代。ADR 0010 仍是 `proposed`，其中后端语言、网页框架和关系数据库产品已被 ADR 0012 取代。ADR 0009 仍是 `accepted`，其中数据库产品的候选已被 ADR 0012 取代。ADR 0022 仍是 `proposed`。其中「等人决定字体」已由 ADR 0024 采纳。不改 0022 正文。ADR 0008 仍是 `accepted`，运行日志仍打到标准输出；文件和审计流由 ADR 0030 增加，不改 0008 正文。ADR 0019 仍是 `accepted`。ADR 0028 确认不做 SQLite，并把第一次真实写入定为 identity 和审计。不改 0019 正文。

2026-11-18 核对：0001 到 0031 都在下表。状态词与各文件开头的 `状态：` 一致。0009 和 0010 的状态行后面还有被取代的说明，正文未改。

2026-11-18：0032 到 0039 已采纳。它们不改 0012、0013、0014、0015、0020、0021、0026、0028、0029、0030 的正文。0039 是 catalog 与 practice 的落库决定，迁移还没写。

2026-11-22：0040 已采纳。生产 CORS 白名单由 `K12_CORS_ORIGINS` 驱动。不改 0032 正文。

2026-11-23：0041 已采纳。收卷照片、卷面匿名和多模态识别见该条。DEC-03 的传输范围以 PRD 为准。不改 0008、0020、0030 的正文。0011 只在文末追加修订说明。

2026-11-24：0042 已采纳。整书导入、书和页命名空间、答案配对。0043 已采纳。答题区大小属于题目，新卷按高度排版，坐标写入 `practice_item_box`。0041 与 0042 只在文末追加修订，不删原文。

2026-11-24：0044 已采纳。二维码在浏览器里用 jsQR 读。服务端核对卷号、页码和出卷老师，后端不加图片库。0041 只在文末追加修订，不删原文。

2026-11-24：0045 已采纳。新增切片 `ai`，两步识别、本机判分、脱敏和失败降级。0004 和 0041 只在文末追加修订，不删原文。

2026-11-24：0046 已采纳。新导入的题分开保存文字和公式，卷面按排版印出，不印 LaTeX 源码。0024 只在文末追加修订，不删原文。不改 0043 正文。

2026-11-25：0047 已采纳。老师按题采用、改判或手评，写入 `teacher_decision`。AI 建议在采用或改判之前不是结论。0041 只在文末追加修订，不删原文。不改 0014、0045 正文。

2026-11-25：0048 已采纳。题目册、答案册、目录可以分开放。页码按册唯一。目录解析成章、节、课时，题目按页码归课。新导入的答案正文带上小问。0042 与 0046 只在文末追加修订，不删原文。

2026-11-25：0042 文末追加 R6b 修订。管理后台 `/admin` 可以拖入或选择书文件夹，先预演再确认写入，调用同一条整书导入接口。规则仍在服务端。不改 0042 上文。

2026-11-25：0045 文末追加 R6a 修订。`GET /api/admin/ai/accuracy` 只读对账，按模型筛选，并给出 0.5–0.9 的阈值测算。默认阈值仍是 0.6。不改 0045 上文。真实样张实测仍未做。

2026-11-25：0049 已采纳。批改确认后按未作废的老师结论再出一份练习。默认 `incorrect`、`partial`、`blank`。不依据未采用的 AI 建议。V019 给 `papers` 增加可空的 `source_paper_id`，无外键、不回填。复用现有出卷。不改原卷。不改 0047 正文。

2026-11-25：0050 已采纳。试用容器由 nginx 终止 TLS，应用和 PostgreSQL 只在容器网络里。不改开发用的 `docker/compose.yml`。自签证书和口令加密只覆盖这一次试用。`#28` 与 `#35` 保持打开。联合备份核对清单，并拒绝恢复到库名 `k12`。不改 0009、0020、0040 正文。

| 编号 | 标题 | 状态 | 切片 |
| --- | --- | --- | --- |
| [0001](0001-long-lived-tier.md) | 按长期项目做 | accepted | 全库 |
| [0002](0002-modular-monolith.md) | 模块化单体 | accepted | 全库 |
| [0003](0003-dependency-rule.md) | 依赖只能向内 | accepted | 全库 |
| [0004](0004-six-slices.md) | 六个深模块 | accepted | 全库 |
| [0005](0005-analysis-ports.md) | 分析用三个端口 | accepted | analysis |
| [0006](0006-versioned-snapshot.md) | 发卷时冻结版本 | accepted | practice |
| [0007](0007-composition-root.md) | 只有一个装配根 | accepted | kernel |
| [0008](0008-logging.md) | 结构化日志和请求 ID | accepted | kernel |
| [0009](0009-files-and-rows.md) | 关系数据和文件分开 | accepted | 全库 |
| [0010](0010-stack-and-deploy.md) | 技术栈和试点部署未拍板 | proposed | 全库 |
| [0011](0011-web-and-desktop.md) | 网页和桌面用同一套界面 | proposed | 全库 |
| [0012](0012-adopt-stack.md) | 采纳第一段的服务端和网页技术栈 | accepted | catalog, practice |
| [0013](0013-draft-and-geometry.md) | 题目草稿契约，几何图先留表位 | accepted | catalog |
| [0014](0014-answer-versions.md) | 答案版本：扫描件和模型候选共用一张表 | accepted | catalog |
| [0015](0015-publication-and-practice.md) | 发布、知识点和多题练习先定列 | accepted | catalog, knowledge, practice |
| [0016](0016-knowledge-and-methods.md) | 知识点和解题方法入库，错因只作建议 | accepted | knowledge, analysis |
| [0017](0017-contract-schema.md) | 草稿形状用 JSON Schema 校验 | accepted | catalog |
| [0018](0018-schema-version.md) | 按契约版本分发草稿 | accepted | catalog |
| [0019](0019-sqlite-second-adapter.md) | SQLite 能不能当第二个适配器 | accepted | catalog, practice |
| [0020](0020-learning-data-retention.md) | 学情保留和删除 | accepted | practice, analysis |
| [0021](0021-integration-proof.md) | 真实阶段前要有一次集成验证 | accepted | catalog, practice |
| [0022](0022-cjk-font-license.md) | 中文字体许可证 | proposed | practice |
| [0023](0023-openapi-types.md) | 用 OpenAPI 生成网页类型 | accepted | practice |
| [0024](0024-system-kaiti.md) | 中文用本机楷体 | accepted | practice |
| [0025](0025-roles-and-session.md) | 角色和会话 | accepted | identity |
| [0026](0026-bootstrap-admin.md) | 首个管理员 | accepted | identity |
| [0027](0027-argon2id.md) | 口令哈希 | accepted | identity |
| [0028](0028-postgres-and-memory.md) | 内存和 PostgreSQL | accepted | identity, kernel |
| [0029](0029-sql-migrations.md) | 迁移 | accepted | identity |
| [0030](0030-log-streams.md) | 运行日志和审计日志 | accepted | kernel |
| [0031](0031-react-router.md) | 网页路由 | accepted | identity |
| [0032](0032-run-mode.md) | 运行模式 | accepted | kernel |
| [0033](0033-session-retention.md) | 会话和登录数据的清理 | accepted | identity |
| [0034](0034-migration-lock.md) | 迁移并发安全 | accepted | kernel |
| [0035](0035-health-ready.md) | 存活和就绪 | accepted | kernel |
| [0036](0036-must-change-password.md) | 首个管理员必须改口令 | accepted | identity |
| [0037](0037-read-audit.md) | 读审计 | accepted | identity |
| [0038](0038-last-admin.md) | 至少一个活跃管理员 | accepted | identity |
| [0039](0039-catalog-persistence.md) | catalog 与 practice 的首个持久适配器 | accepted | catalog, practice |
| [0040](0040-cors-origins.md) | 生产 CORS 白名单由 K12_CORS_ORIGINS 驱动 | accepted | kernel |
| [0041](0041-intake-photo-and-vision.md) | 收卷照片与多模态识别 | accepted | practice |
| [0042](0042-book-import.md) | 整书导入：书和页命名空间、答案配对 | accepted | catalog |
| [0043](0043-answer-space-and-layout.md) | 答题区大小与按高度排版 | accepted | catalog, practice |
| [0044](0044-browser-qr-decode.md) | 二维码在浏览器里读 | accepted | practice |
| [0045](0045-ai-suggestions.md) | AI 识别建议 | accepted | ai |
| [0046](0046-formula-layout.md) | 卷面公式按排版印出 | accepted | catalog, practice |
| [0047](0047-teacher-decisions.md) | 老师确认或手评成为正式结论 | accepted | practice |
| [0048](0048-book-volumes-and-lessons.md) | 题目册、答案册和目录 | accepted | catalog, practice |
| [0049](0049-follow-up-paper.md) | 从已确认批改再出一份练习 | accepted | practice |
| [0050](0050-trial-docker-and-backup.md) | 单机试用的容器、HTTPS 和联合备份 | accepted | 全库 |
