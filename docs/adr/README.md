# ADR 索引

状态只用三个词：`proposed`、`accepted`、`superseded`。每条 ADR 开头有同样的状态行。正文里的日期和原句不改。

没有整条被取代。ADR 0010 仍是 `proposed`，其中后端语言、网页框架和关系数据库产品已被 ADR 0012 取代。ADR 0009 仍是 `accepted`，其中数据库产品的候选已被 ADR 0012 取代。ADR 0022 仍是 `proposed`。其中「等人决定字体」已由 ADR 0024 采纳。不改 0022 正文。

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
