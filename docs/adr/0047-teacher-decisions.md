# ADR 0047 老师确认或手评成为正式结论

状态：accepted

## 背景

R6 已经能对收卷照片生成 AI 建议（`ai_run`、`ai_suggestion`）。老师页当时只读。`POST /api/practice/confirmations` 的 adopt / revise / reject 仍挂在合成作答上：出卷时 `synthetic_attempt_text()` 放进「学生写下了 5」。真实闭环缺的是老师按题看建议，然后采用、改判，或者在没有可用建议时直接手评。结果要成为正式结论。

catalog 的 `answer_decision`（ADR 0014）是老师记下 OCR 与模型对答案草稿的分歧。那张表仍未建。本批不建它，也不用它。

路线图顺序改为 R7 在 R6a 之前。R6a 用老师结论对照 `ai_suggestion` 测识别率，并定 `K12_AI_REVIEW_THRESHOLD`。见 #103。

## 选项

1. 继续用 `confirmations`，把合成作答换成对照片题的确认。
2. 新建 `answer_decision`，把草稿分歧和卷面批改放进同一张表。
3. 新建 `teacher_decision`。每张卷的每道题同时只有一条未作废结论。来源是 adopted、revised、manual。AI 建议在采用或改判之前不是结论。

## 决定

选 3。

### 数据

V017 建 `teacher_decision`。不改写已有 `confirmations` 行，不改已发出的卷。

每张卷的每道题，`voided_at` 为空的结论至多一条。改判时旧行写下 `voided_at`，新行生效。

必须有：`paper_id`、`order_no`、`verdict`（`correct` | `incorrect` | `partial` | `blank`）、`decided_by`、`decided_at`、`source`（`adopted` | `revised` | `manual`）。

`source` 为 `adopted` 或 `revised` 时，记下当时的 `ai_run_id`、AI 的 verdict 和置信度。建议以后被替换，这三列仍能对账。`ai_run_id` 不设外键：V015 的 down 会删 `ai_run`，当时更晚的表还在。可选：老师修正后的转写、一句评语。`source` 为 `manual` 时，这些列为空。

`adopted` 记为与 AI 一致。`revised` 记下 AI 原来的 verdict 和置信度；老师结论与 AI verdict 相同则一致，否则不一致。`manual` 不引用建议，记为不一致。

### 当前建议

一张卷可以有多次 run（重试、换照片）。当前建议是这道题所在页、当前照片（`superseded_at` 为空）上，最近一次成功 run 的建议。最近按 `finished_at`、`started_at`、`run_id`。失败的重试不换掉更早的成功。后一次成功整次换掉前一次成功，不按题号拼旧 run。

照片被替换后，旧照片上的建议不再是当前建议。对它采用或改判返回 `suggestion_stale`。

### 三种来源

- `adopt`：verdict 取自当前 AI 建议。建议是 `unsure` 时不能采用，返回 `cannot_adopt_unsure`。
- `revise`：老师另选 verdict，可改转写、写评语。必须有当前建议。
- `manual`：没有当前建议时只能走这一条。不写入 AI 列。

### 一次采用高把握

`POST /api/practice/papers/{paper_id}/decisions/adopt-confident` 只采用同时满足这些条件的建议：本机判、置信度不低于阈值、不是 `unsure`、这道题还没有当前老师结论。阈值是 `K12_AI_REVIEW_THRESHOLD`，空或不可用时是 0.6。等于阈值不算「需要老师看」。

服务端不自动采用。老师要点按钮。页面先列出将采用的题号，老师确认后才写入。

需要老师看：看不清，或置信度低于阈值。这些题排在批改页前面。

### 界线

AI 建议只有经老师 `adopt` 或 `revise` 才成为正式结论。手评是老师自己的结论，不把建议当成结果。

审计事件 `teacher_decision_saved`。明细只有 `paper_id`（内部编号）、`order_no`、`action`、`verdict`、`agrees`。不带学号、转写、评语。

读接口是 `GET /api/practice/papers/{paper_id}/review`。响应不带学号。

### 旧确认路由

`POST /api/practice/confirmations` 只剩合成流程和测试在用。development 保留。production 返回 410，`code` 是 `confirmations_retired`，正文写明改用 `PUT /api/practice/papers/{paper_id}/items/{order_no}/decision`。不删除已有 `confirmations` 行。

production 下出卷不调用 `synthetic_attempt_text()`，也不再为确认绑定合成作答。

## 后果

R6a 用 `teacher_decision` 与 `ai_suggestion` 对账，测识别率，并据此改定 `K12_AI_REVIEW_THRESHOLD`。见 #103。

按题裁切仍未做。再出一份练习是 R8。`answer_decision` 仍未建。

权限：只有出这张卷的老师和管理员。写操作要 CSRF。
