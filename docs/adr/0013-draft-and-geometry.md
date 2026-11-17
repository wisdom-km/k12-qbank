# ADR 0013 题目草稿契约，几何图先留表位

## 背景

核对页在另一个仓库里对照原 PDF 修改 Markdown，并拆出题目草稿。题库已经选定 PostgreSQL，但这一段还没有连接，也没有迁移。图形现在是裁图。以后要存可编辑几何图。

## 选项

1. 现在就建 PostgreSQL 表，把裁图和几何图都写进去。
2. 两个仓库先共用一份草稿契约。裁图只是坐标。可编辑几何图留一个空位和未来的表名，这一段不建表。

## 决定

选 2。

- 契约名是 `k12-question-draft`，版本是 1。catalog 用 `parse_question_draft` 读取。整页 OCR 块列表拒绝。
- 草稿不能变成发布记录。老师确认题型之后仍然要另有核准的题目版本和答案版本。
- 裁图是 `assets` 里的 `crop`，只保存四个坐标。文件本体仍按 ADR 0009 放在文件存储。
- 可编辑几何图的未来表名是 `figure_geometry`。列是题目版本、可空的来源裁图、`kind`、`document`。契约里的 `geometry` 为 `editable-geometry` 第 1 版，`document` 原样保留，现在不解释。
- 这一段不连接 PostgreSQL，不加迁移。第一次真正写入数据库时，同一改动里再加可回退的迁移，并包含 `figure_geometry`。
- 题目表不按题型拆开。`type` 是文字代码，`structure` 决定用哪些子行。现在的结构只有 `choice`、`blank`、`worked`、`composite`、`unresolved`。
- 判断题、作图题这类以后的题，先在 `TYPE_STRUCTURE` 加一行，分别复用选项行或几何图位，不新建题目表。
- 综合题的代码是 `composite`。它仍是一条题目。共用题干在题目上，至少两个小问，每个小问自带 `type`。小问不能再套综合题。核对页现在不会自动写出这个代码。
- 连线、排序这类现有子行放不下的形状，以后才加子表，并同时给 `structure` 加新代码。在那之前，未知代码会被拒绝。
- 组卷里的「综合」是知识点角色，不是 `composite`。主要考查走专项，辅助使用走综合练习。

## 一步导入

核对页写完的 `.questions.json` 就是导入文件。catalog 的 `import_question_draft` 解析一次并保存。不再把题干、选项或小问转换成另一套 JSON。

整页 OCR 块列表在这一步被拒绝，不会入库。草稿保存之后仍不是发布记录。老师还要另有核准的题目版本和答案版本，才能出卷。参考答案不在这份题目文件里。扫描件和模型生成的答案见 ADR 0014。

现在保存在内存里。第一次连接 PostgreSQL 时，迁移建立下面这些表，适配器用同一次解析结果插入。列和草稿字段同名，不再做字段映射。

| 表 | 行从哪来 |
| --- | --- |
| question_version | 一题一行。`type`、`structure`、`status`、`stem`、`section`、`number`、来源页 |
| question_option | 题目或综合题小问上的一个选项 |
| sub_question | 一个小问。综合题的小问带自己的 `type` 和 `structure` |
| question_asset | 一个 `crop` 和四个坐标 |
| figure_geometry | `geometry` 不是空的时候才有行。现在不建表 |

`question_version_id` 在核准发布时才分配。它是新的标识，不改题干内容。

## 后果

核对页可以继续只写草稿文件。题库能认出这份文件，也能拒绝把它当正式题发出。几何图编辑器还没有。

## 状态

采纳。2026-11-17。不取代 ADR 0009 的「图形先是图片」，只为以后的几何图留表位。
