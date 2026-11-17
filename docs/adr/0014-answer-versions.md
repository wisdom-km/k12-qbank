# ADR 0014 答案版本：扫描件和模型候选共用一张表

状态：accepted

## 背景

题目草稿已经有契约和将来的表，见 ADR 0013。答案还没有同等的列。参考答案有两个来源：核对页扫进来的纸质答案，以及多模态模型生成的答案和过程。方案要求两者都留下，不一致时由老师判断。学生写在卷上的字是另一件事。

这一段仍不连接 PostgreSQL，也不加迁移。

## 选项

1. OCR 答案一张表，模型答案另一张表。
2. 一张 `answer_version`。`origin` 用代码区分来源。小问、步骤、裁图和老师的分歧各自用子表。

## 决定

选 2。来源是行上的代码，不是一张来源一张表。这和题目不按题型拆表相同。

- 契约名是 `k12-answer-draft`，版本是 1。一份文件是一条答案，不是整页 OCR 块列表。整页块列表拒绝。
- 文件键只有这些：`contract`、`contract_version`、`schema_version`、`ok`、`reason`、`question_key`、`key`、`origin`、`status`、`applicable`、`source`、`content`、`parts`、`assets`。`schema_version` 的分发见 ADR 0018。
- `question_key` 对上题目草稿的 `key`。`key` 在同一题内唯一，形状是 `题键:来源:序号`，例如 `1:1:ocr:1`。
- `origin` 只接受 `ocr`、`model`、`teacher`。未知代码拒绝。
- `ocr` 的 `source` 只有 `pdf_page`。扫描件本体按 ADR 0009 放文件存储，行里不放图片字节。
- `model` 的 `source` 只有 `model_task_id`。不放提示词，不放供应商原文。
- `teacher` 的 `source` 是空对象。它是老师改出的新版本，不覆盖原来的 `ocr` 或 `model` 行。
- `status` 只接受 `candidate`、`needs_confirm`、`confirmed`、`disputed`。
- `content` 和题目题干用同一套片段：`text` 加 `value`，或 `math` 加 `latex`。选择题的结果写选项字母，不抄选项正文。
- `parts` 的每一项只有 `sub_key`、`role`、`order`、`content`。`role` 只接受 `result` 和 `step`。`sub_key` 对上题目小问。
- `assets` 的每一项只有 `role` 和 `bbox`。`role` 这一步只接受 `crop`。`bbox` 是四个数。
- `applicable` 表示这条能不能作为出卷用的那一条。`origin` 为 `model` 时必须是 false。同一 `question_key` 最多一条 `applicable` 为 true，且它的 `status` 必须是 `confirmed`。
- 同一题可以有多条答案，用来留下多种解法。导入不把两条合并成一条。
- 老师记下 OCR 和模型不一致时，另写 `answer_decision`。它不在导入文件里。列是 `question_key`、两个候选 `key`、选定的 `key`、短原因。两条候选都保留。
- 答案草稿不是发布记录。`answer_version_id` 在核准时才分配，是新标识，不改内容。题目版本和这条答案都核准之后才能出卷，见 ADR 0006。
- 学生写在卷上的内容留在 practice 的作答。不写入 `answer_version`。
- 核对页把一页 OCR 答案写成多份文件，每份就是一条答案。文件名只是把 `key` 里的冒号换成连字符，例如 `1:1:ocr:1` 存成 `1-1-ocr-1.json`。JSON 里的 `key` 仍用冒号。`parse_answer_draft` 解析一次，`import_answer_draft` 按 `key` 保存。不再转成另一套 JSON。写入和读入前先按 ADR 0017 的 JSON Schema 校验形状。核对页只写 `origin` 为 `ocr` 的文件。模型候选仍由分析端口产生。这一步仍不连接 PostgreSQL，也不建表。

## 连库

第一次把一行答案写入 PostgreSQL 时，同一改动里加可回退的迁移，并插入同一次解析结果。列名和文件键相同。没有要写入的答案时，不提前建这些表。题目和答案同一次写入时，用同一份迁移，题目表仍按 ADR 0013。

| 表 | 行从哪来 |
| --- | --- |
| answer_version | 一份 `k12-answer-draft`。含 `origin`、`status`、`applicable`、`content`、`source`、`question_key`、`key` |
| answer_part | `parts` 的一项 |
| answer_asset | 一个 `crop` 和四个坐标 |
| answer_decision | 老师记下的分歧。现在不建表 |

## 后果

以后接入数据库时，先读本条、ADR 0013、ADR 0012、ADR 0009 和 ADR 0006。不要为扫描件和模型各做一套题目 JSON，也不要把模型候选标成可出卷。

## 状态

采纳。2026-11-17。不取代 ADR 0006。只补上答案版本的列和来源。列已写明，表仍未建。
