# 执行计划：knowledge 切片的内存目录

状态：进行中。2026-11-20。这一段把 `knowledge` 放进 `PHASE_SLICES`。`catalog`、`practice` 和 `identity` 仍在。`analysis` 和 `delivery` 仍不建目录。

有理数合成闭环停在 [rational-number-loop.md](rational-number-loop.md)。登录和审计停在 [identity-and-audit.md](identity-and-audit.md)。本文件只覆盖知识点和解题方法的内存目录。

## 决定

- 知识点仍按 ADR 0015。解题方法仍按 ADR 0016。错因只作建议，不进本切片。见 ADR 0005 和 PRD 的 R3。
- 端口是 `KnowledgePoints`、`Methods`、`QuestionTagger`。内存实现是 `MemoryKnowledgePoints`、`MemoryMethods`、`MemoryTagger`。
- `MemoryTagger` 构造时注入 `KnowledgePoints`、`Methods` 和 `CatalogReader`。挂标签时各读一次目录和一次已核准题目。
- 一条题目版本最多一个 `primary`。综合题的知识点只能是 `support`。方法不看题型，不设主次。
- 题目学科和目录学科不同，拒绝 `subject_mismatch`。
- 没有标签的已核准题可以留在 catalog，按知识点检索不返回它。
- catalog 的 `ApprovedQuestionReader` 只包 `read_snapshot`，返回时带上 `structure`。它不导入 knowledge。
- 调用方只匹配 `KnowledgeFault.code`。`message` 只给日志，不进接口正文。
- 没有要写入的行，不建 PostgreSQL 表，不写 V006。

## 完成线

内存适配器和契约测试通过。PostgreSQL 分支留到第一次真正写入知识点或解题方法的那一批。

2026-11-20：端口、内存适配器、catalog 薄壳和 `tests/knowledge` 已接上。单测见 `docs/evidence/knowledge-memory-2026-11-20.md`。

## 还不做

- 不提供 `untag_point` / `untag_method`。
- 不提供 retag（改 `role`）。
- 后果：当前要修正一次挂错只能 rename knowledge point 或 method。此为已知限制，等 UI 出现误操作案例后另开批次补。
- `publication`、`publication_asset`、`source_work`、`practice_item`。
- `figure_geometry`、`answer_decision`。
- knowledge 的 PostgreSQL 适配器和 V006。
- 知识点管理页和标签挂载页。
- analysis 的建议、错因和模型输出。
- M-14 的外部接收方。issue #47 仍开着，本批不关闭、不改标签。
