# 执行计划：规范化题目表与答案表

状态：D1 已接入。2026-11-19。

## 决定

- 迁移是 `backend/catalog/migrations/V004__questions_answers.sql`。版本号全局唯一，所以不用已被 identity 占用的 `V001`。
- 表是 `questions` 和 `answers`。ADR 0013、0014 的子表这次不建。ADR 正文不改。
- 主键是 `question_id` 和 `answer_id`。`approvals` 不设到这两张表的外键。
- `origin` 仍是 `ocr`、`model`、`teacher`。`source` 仍是草稿里的对象。
- `questions.created_at` 和 `approved_at` 非空。`answers` 没有时间列。
- 同一个 `key` 再保存时插入新的 `version`，不改旧行正文。旧的可出卷答案只把 `applicable` 改成 false，以便新行成为这一题唯一的可出卷行。
- 核准快照没有题型。题目和答案都核准时插入一行：`type` 用 `unresolved`，题干写成一个 text 片段，答案 `origin` 用 `teacher`。已有的 `question_id` 不再改。
- `K12_PG_DSN` 为空时，development 仍用内存。production 没有连接串仍退出。

## 证据

`docs/evidence/catalog-normalized-tables-2026-11-19.md`。空库做过向前、回滚、再向前。

## 还不做

`question_option`、`sub_question`、`question_asset`、`figure_geometry`、`answer_part`、`answer_asset`、`answer_decision`。knowledge、analysis、delivery 的目录。M-14 的外部接收方。#47 保持打开。
