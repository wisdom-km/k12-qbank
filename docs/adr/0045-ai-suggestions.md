# ADR 0045 AI 识别建议

状态：accepted

## 背景

ADR 0041 把多模态分成两步：先转写学生作答，再对照标准答案判断。看不清不记为做错。AI 建议在老师确认之前不是结论。模型是火山引擎方舟，由 `K12_AI_MODEL` 配置，不开长思考。传给第三方的范围以 DEC-03 为准。姓名在任何情况下不出境。调用失败不挡老师确认。

ADR 0004 里，`analysis` 管的是模型差异、任务和候选题，目录仍未建。本批要落的是对照片做一次识别并给出建议。`practice` 已经管出卷、收卷和确认。把供应商 HTTP 写进 `practice`，会让确认规则绑上火山引擎。

用户已定：选择题，以及填空里纯数字或纯字母的答案，在本机按规则比对，不发给模型。只有计算题、解答题，以及本机判不了的填空，才把题干、标准答案和转写结果发给模型判断。

issue #101：模型读出照片上印的学号和页码，和收卷定位的结果比对。不一致时提醒老师。不存模型读回的学号原文。

## 选项

1. 把识别写进 `practice`。端口和火山引擎客户端放在同一目录。
2. 把识别写进 `analysis`。ADR 0005 的端口是作答分析、练习推荐和任务，目录仍未建。
3. 新增切片 `ai`。端口 `VisionModel` 只有转写和判断。建议不写进确认表。适配器有 mock 和 volcengine。组合根按 `K12_AI_PROVIDER` 装配。

## 决定

选 3。

### 为什么加切片

识别的变化来自提示词、模型、超时和脱敏，不来自确认规则。单独一个切片，practice 继续只通过普通数据拿建议，不导入火山引擎客户端。`scripts/check.conf` 的 `PHASE_SLICES` 加上 `ai`。`analysis` 和 `delivery` 仍不建目录。ADR 0004 的决定句不改。

### 端口

`VisionModel` 两个方法：

- `transcribe(image_bytes, items)`：每题的转写、是否看不清、置信度（0 到 1），以及照片上读到的学号和页码。
- `judge(items_with_answers_and_transcriptions)`：每题的判断，取 `correct`、`incorrect`、`partial`、`unsure` 之一，并给出依据。

### 适配器

- `mock`：确定性的假结果。测试可以让它模拟看不清、超时和输出不合格。测试、CI 和开发环境默认用它。
- `volcengine`：方舟 OpenAI 兼容的 chat completions。地址、模型、密钥分别来自 `K12_AI_BASE_URL`、`K12_AI_MODEL`、`K12_AI_API_KEY`。关闭深度思考的参数是请求体顶层 `"thinking": {"type": "disabled"}`。JSON 输出是 `"response_format": {"type": "json_object"}`，提示词正文里写明 JSON。超时取 `K12_AI_TIMEOUT_SECONDS`，空或不是正数时用 60。HTTP 客户端用仓库里已经钉死的 httpx 0.28.1，`trust_env=False`。不加 openai SDK，也不新加包。

`K12_AI_PROVIDER` 取 `mock` 或 `volcengine`。空则是 mock。production 下选了 volcengine，但缺地址、模型或密钥：启动失败，标准错误写出缺的变量名，不打印密钥。其他取值在任何模式下启动失败，不静默落到 mock。development 下选了 volcengine 但缺变量：进程可以起来，调用时返回 `ai_provider_incomplete`，仍然不打印密钥。

### 两步各发什么

转写只发：照片；每题的题号；答题框按页面宽高换成 0 到 1 的相对坐标；题型。不发标准答案，不发题干。

判断只发：题干、标准答案、转写结果、题型。不发照片。

两步都不发：姓名、内部 `student_id`、`paper_id`、`intake_id`、老师信息、学号文本。照片上印着的学号随图片出去，这在 DEC-03 的范围内。

标准答案取发卷时冻结在练习题上的 `answer_text`，不取后来改过的题库。

### 本机判和模型判

选择题：转写去掉空格，全角转半角，大小写统一，多选按字母排序，再和标准答案比对。

填空题：每个空分别比对。只有纯数字（含负号和小数）或纯字母时本机判。其余交给模型。

看不清的题不判。结果记 `unsure`，依据写「看不清」。

每条建议记下 `judged_by`：`local` 或 `model`。

### 学号和页码只存比对结果

模型读回的学号只和 `papers.printed_external_id` 比对。页码只和这张收卷的页码比对。`ai_run` 只存 `consistent`、`mismatch` 或 `unread`。不存模型读回的原文。两边都空，记 `unread`。卷上的印刷学号为空、模型读到非空，记 `mismatch`。

模型返回必须整份符合约定形状。不合格整次记 `model_output_invalid`。不猜测，不部分采用。本机已经判完的题也不单独落库。

### 失败、上限、提示词版本

建议写在 `ai_suggestion`。`confirmations` 不写这些行。确认前不是老师结论。

超时、网络、鉴权、输出不合格、每日上限和进程中断，只把这一次 `ai_run` 记成 `failed`。收卷状态和老师确认不受影响。

同一张照片已有 `queued` 或 `running` 时，再次开始返回 `ai_run_in_progress`。每日上限是 `K12_AI_DAILY_LIMIT`，默认 500，按 UTC 日计数已经开始的次数（含失败）。到了返回 `ai_daily_limit`，并且不插入新行。

提示词在 `backend/ai/prompts/`，文件名带版本。当前版本字符串是 `transcribe-v1/judge-v1`。每次运行记下这个字符串。提示词正文不进日志，不进审计。

后台用标准库线程池，最多 2 个并发。服务启动时，仍是 `queued` 或 `running` 的记录改成 `failed`，`error_code` 为 `interrupted`。

老师页上，「需要老师看」先写死置信度低于 0.6，或这一题看不清。等于 0.6 不标。真实样张上的阈值是 R6a，不在这里定。采用、修改、驳回建议的界面是 R7。按题裁切仍按 ADR 0041 第 6 条，本批不做。

## 后果

- 迁移 V015 建 `ai_run` 和 `ai_suggestion`。SQL 放在 catalog 的迁移目录，因为仓库只有这一处迁移运行器。确认表不改。
- 审计事件 `ai_run_started` 和 `ai_run_finished` 只带 `run_id`、provider、model、status、耗时和 token 数。不带学号、照片、转写、提示词和密钥。
- 路线图第 3 节当时写的是 `PageReading`、`student_token`、`K12_VOLCENGINE_API_KEY` 和标准库 HTTP。那些句子留在原处。本条是后来的落法：环境变量是 `K12_AI_BASE_URL`、`K12_AI_MODEL`、`K12_AI_API_KEY`；适配器用已钉死的 httpx；不持久化模型读回的学号原文；发给第三方的文字里不放 `student-N`。拍板记录第 8 条的原句不改。本批的文字请求不使用那一条里的 `student-N`。
- 测试、CI 和本机门禁只用 mock，不调用真实火山引擎。手动探测是 `scripts/ai_probe.py`，见 [docs/ops/ai.md](../ops/ai.md)。

## 状态

采纳。2026-11-24。

## 修订（2026-11-25，R6a 对账报表）

管理员只读 `GET /api/admin/ai/accuracy`。查询参数 `provider`、`model` 可省略。省略时统计全部运行和全部未作废老师结论。写上时去首尾空白后精确匹配 `ai_run.provider`、`ai_run.model`。运行计数只含匹配的运行。老师结论只计入其 `ai_run_id` 落在这些运行里的记录；没有 `ai_run_id` 的纯手评归入 `unlinked_manual`，不进该模型的分子分母；指向其他模型的结论整行不进这一次筛选。响应另给库里出现过的不重复 `(provider, model)`，不含密钥和地址。

关联键是 `teacher_decision.ai_run_id` 加上 `paper_id`、`order_no`，对上同一次运行里的 `ai_suggestion`。已作废结论（`voided_at` 非空）不计入。存储里的判定是 `correct`、`incorrect`、`partial`、`unsure`，没有 `wrong`。对账里的「错」就是 `incorrect`。有把握是看清了且判定为 `correct` 或 `incorrect`。看不清或 `unsure` 计入不确定。`partial` 两边都不进。学号和页码只统计成功运行：库存的 `consistent`、`mismatch`、`unread`（或空）分别记成 `matched`、`mismatched`、`missing`。

阈值表固定算 `0.5`、`0.6`、`0.7`、`0.8`、`0.9`。当前生效值读 `K12_AI_REVIEW_THRESHOLD`，与批改里同一函数，空着或不可用仍是 `0.6`。若当前值不在这五档里，并入后按升序去重。某一档的高把握题是有把握且置信度大于等于该档。高把握却和老师结论不同的题数是 `false_confident`。覆盖率是高把握题数除以关联到建议的题数。分母为 0 时比率为空，不除零。本修订不改默认阈值，不改提示词，不改批改写入。

成功读取不写审计。响应只有计数、比率、provider、model 和错误码计数。不返回学号、姓名、题干、标准答案、转写、改正转写、批注或文件路径。真实样张实测、模型选型和阈值拍板仍未做。步骤见 [docs/ops/ai-accuracy.md](../ops/ai-accuracy.md)。上文不改。
