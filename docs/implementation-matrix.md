# 实现矩阵

日期：2026-11-18。六行是 ADR 0004 的六个切片。只记仓库里已经有的实现。

PostgreSQL 还没连接，没有迁移，也没有空表。内存适配器不是持久适配器。`MemoryFiles` 只在进程内存里放字节，不是磁盘或对象存储。一个端口要同时有内存实现和至少一个持久实现，并且契约测试两边都跑，才算真接缝。现在没有持久适配器，所以这六行都还不是真接缝。

日志的 `StdoutLogger` 在组合根，不属于这六个切片。

契约测试指：每个端口一套测试，假适配器和真实适配器都跑。草稿形状的 schema 测试算 core 测试，不算这一列。端到端未写。`test_http_loop` 是本机合成 HTTP，不是端到端。

改了某一格，同一个 PR 里改本表，并勾选 PR 模板里的对应项。

| 切片 | 端口 | 内存适配器 | 持久适配器 | core 测试 | 契约测试 | 端到端 | 文档 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| catalog | 题目草稿、答案草稿、核准写入 | `MemoryDrafts`、`MemoryAnswers`、`MemoryApprovals` | 无 | `test_question_draft`、`test_import_draft`、`test_import_answer`、`test_contract_schema`、`test_review_import` | 未写 | 未写 | ADR 0013、0014、0017、0018 |
| knowledge | 文档里有查询知识点。代码里没有 | 无 | 无 | 无 | 未写 | 未写 | ADR 0015、0016。切片目录未建 |
| identity | 授权。ADR 0004 把授权先放在 practice | 无单独切片。`MemoryAuth` 在 practice | 无 | 无单独切片 | 未写 | 未写 | ADR 0004。切片目录未建 |
| practice | 练习存储、文件、单页渲染、授权 | `MemoryPractice`、`MemoryFiles`、`MemoryAuth`。`StdPdf` 是标准库渲染，不是存储 | 无 | `test_core_loop`、`test_paper_status`、`test_confirm_rules`、`test_http_loop`、`test_m1_review`、`test_service_probe` | 未写 | 未写 | ADR 0006、0015 |
| analysis | 作答分析、练习推荐、任务。只在架构文档 | 无 | 无 | 无 | 未写 | 未写 | ADR 0005、0016。切片目录未建 |
| delivery | 排版和导出。代码里没有这个切片 | 无。面向学生的单页 PDF 在 practice 的 `StdPdf` | 无 | 无 | 未写 | 未写 | ADR 0004。切片目录未建 |
