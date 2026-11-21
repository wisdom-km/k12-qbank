# 执行计划：多题练习 practice_item

状态：进行中。2026-11-21。这一段只覆盖多题练习的落库和读取兜底。有理数合成闭环停在 [rational-number-loop.md](rational-number-loop.md)。知识点停在 [knowledge-slice.md](knowledge-slice.md)。

## 决定

- 列按 ADR 0015 第 7 条。表是 `practice_item`：`paper_id`、`order_no`、`question_version_id`、`answer_version_id`、`score`。分值没有机构规则时留空。`order` 是保留字，字段用 `order_no`。
- 数据库不加 `order_no >= 1`。小于 1 或重复的顺序在写入时拒绝。外键只指向 `papers`，删除行为保持 RESTRICT。不指向题目表或答案表。
- 不在 catalog 增加端口、方法或字段。适用答案就是 `ApprovalPort.read_snapshot` 带回的 `answer_version_id`。ADR 0014 规定同一 `question_key` 最多一条 applicable 为 true，且它的 status 必须是 confirmed。ADR 0015 规定发布记录把一条已核准题目版本和一条适用答案版本绑在一起。快照上的答案版本就是那条。
- 检查在 practice 的 `_is_item_approved`，顺序固定：快照不存在，题目未核准，答案未核准，答案版本与快照不一致。任一拒绝都不留下 paper、page 或 practice_item。
- 旧的单题写入仍只写 `papers`，不写 `practice_item`。`papers.question_version_id` 不删、不改约束。多题写入把传入序列的第一条抄进这个兼容列。
- 读取走 `_resolve_items`。有行就按 `order_no` 升序返回。没有行就把卷上的版本号包成一条 `order_no = 1`、`score` 为空的项。
- 版本号 V006 给这张表。knowledge 的表仍未建。

## 完成线

旧单题卷不回归。新多题卷顺序冻结。契约测试在内存上每次都跑，PostgreSQL 在 `K12_PG_DSN` 有值时跑同一套。

2026-11-21：端口、内存适配器、PostgreSQL 适配器和多题写入已接上。契约见 `tests/practice/test_practice_item_contract.py`。空库核对见 `docs/evidence/practice-item-2026-11-21.md`。

## 还不做

- `publication`、`publication_asset`。
- retire 语义，以及 active / retired 状态转换。
- 分值校验规则。
- 以上都留给 D5。
- HTTP 出卷路由仍走旧的单题写入。本批不改那条路由。
- `source_work`、knowledge 的 PostgreSQL 表、`figure_geometry`、`answer_decision`。
- M-14 的外部接收方。issue #47 仍开着，本批不关闭、不改标签。
