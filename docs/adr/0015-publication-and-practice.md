# ADR 0015 发布、知识点和多题练习先定列

状态：accepted

## 背景

ADR 0013 规定题目草稿怎么入库。ADR 0014 规定参考答案。正式出卷还要有发布记录。老师检索要有知识点。一套练习通常有多道题。现在的学生卷只冻结一个题目版本。这些对象还没有表，也还没有数据库。

## 选项

1. 第一次连接 PostgreSQL 时把发布、知识点、练习册和多题卷全部建出来，即使没有行。
2. 现在写清列，以及每一类第一次写入时才建表。没有行就不建空表。

## 决定

选 2。下面的顺序是产品规则。没写「已做」的，代码里还没有。

1. 题目草稿进入 catalog。已做。草稿不能出卷。
2. 答案草稿按 ADR 0014。OCR 文件和 `import_answer_draft` 已做。确认后仍不能出卷。`origin` 为 `model` 的行不能作为出卷用的那一条。
3. 老师确认题型，并选定一条状态为 `confirmed` 且 `applicable` 的答案。这一步不改题干。
4. 核准时才分配 `question_version_id` 和 `answer_version_id`。它们是新标识。草稿保留。
5. 发布记录把一条已核准题目版本和一条适用答案版本绑在一起。没有发布记录，不能正式出卷。
6. 知识点可以后标。没有标签的题可以保存和核准，但不能出现在按知识点的检索里。老师仍可用题号把它放进练习。
7. 一套练习可以有多道题。现在的学生卷仍只有一个 `question_version_id`。多题用 `practice_item`，不把题单塞进这一个字段。补打沿用原卷次。新一轮练习用新卷次。
8. 学生作答、缺页、照片和模型建议不进 catalog 的这些表。这一段仍只建 `catalog` 和 `practice` 目录。

| 表 | 何时建 | 列 |
| --- | --- | --- |
| publication | 第一次发布一条题 | `publication_id`、`question_version_id`、`answer_version_id`、`layout_template_id`、`subject_id`、`status`。`status` 只接受 `active` 和 `retired` |
| publication_asset | 同一次发布 | `publication_id`、文件标识。文件本体仍按 ADR 0009 |
| knowledge_point | 第一次保存一个知识点 | `knowledge_point_id`、`subject_id`、显示名、章节显示名 |
| question_knowledge | 第一次给一条题目版本打标签 | `question_version_id`、`knowledge_point_id`、`role`。`role` 只接受 `primary` 和 `support`。一条题目版本最多一个 `primary`。综合练习是 `support` |
| source_work | 第一次登记一册练习册 | `source_id`、文件标识、显示名。题目草稿上的 `pdf_page` 继续表示页码 |
| practice_item | 第一次把第二道题放进同一套练习 | `paper_id`、顺序、`question_version_id`、`answer_version_id`、分值。分值没有机构规则时留空 |

解题方法是另一张目录，错因只作建议。列和边界见 [ADR 0016](0016-knowledge-and-methods.md)。不要把做法名称或某次错因写进题目行。

现有的单题字段保持不变，直到实现 `practice_item` 的那次改动。那次改动要带测试：旧的单题卷仍能打开，新的多题卷按顺序冻结。

## 后果

连库时先读 ADR 0012、0013、0014 和本条。只建这次真正要插入的表。检索页没有标签就不要把题显示出来。不要为了多题练习去改已发出卷上的单个版本号。

## 状态

采纳。2026-11-17。不取代 ADR 0006。补上发布记录、知识点和多题练习的列。
