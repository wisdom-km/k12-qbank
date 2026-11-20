# 执行计划：题目和答案的子表

状态：D2 已接入。2026-11-20。

## 决定

- 迁移是 `backend/catalog/migrations/V005__catalog_subtables.sql`。不改 V001 到 V004 的原文。
- 五张子表是 `question_option`、`sub_question`、`question_asset`、`answer_part`、`answer_asset`。
- 父行仍是 `questions.question_id` 和 `answers.answer_id`。子表外键指向这两列。
- 行标识是 text。`position` 记住数组顺序。`answer_part` 用草稿里的 `order`。
- `stem`、`content`、`bbox` 仍是 jsonb。V004 上的嵌套列还在。
- 非综合题小问的 `type` 和 `structure` 可以同时为空。`answer_part.sub_key` 不设外键。
- `figure_geometry` 和 `answer_decision` 仍不建。ADR 正文不改。
- `approvals` 增加可空的 `type` 和 `structure`。核准写入只在这是一对真实题型时插入题目行和答案行，不再写 `unresolved`。没有题型时不插入这两行。已有的 `question_id` 不改。
- 同一个草稿 `key` 再保存时插入新版本，并带上新的子行。旧行和旧子行留着。
- `scripts/backfill_question_type.py` 只在显式 `--apply` 时改行。检查和 CI 不调用它。
- `K12_PG_DSN` 为空时，development 仍用内存。production 没有连接串仍退出。

## 证据

`docs/evidence/catalog-subtables-2026-11-20.md`。空库做过向前、回滚、再向前。本机库只做了 dry-run。

## 还不做

`figure_geometry`、`answer_decision`。knowledge、analysis、delivery 的目录。practice 的规范化表。M-14 的外部接收方。#47 保持打开。
