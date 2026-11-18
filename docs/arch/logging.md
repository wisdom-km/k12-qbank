# 运行日志事件

谁看、级别和绝不记仍在 [ARCHITECTURE.md](../../ARCHITECTURE.md) 的「运行日志」。下面是事件表。

要记的事件：

| 事件 | 级别 | 哪一层 | 额外字段用标识，不用正文 |
| --- | --- | --- | --- |
| http_completed | INFO | HTTP 入口 | 路径模板、状态码、duration_ms |
| use_case_refused | WARN | 用例 | 错误码 |
| use_case_failed | ERROR | 用例 | 错误码 |
| adapter_completed | INFO | 适配器 | 端口名、结果、duration_ms |
| adapter_failed | ERROR | 适配器 | 端口名、错误码、duration_ms |
| question_published | INFO | catalog | 发布记录标识 |
| draft_imported | INFO | catalog | 导入的题目数。不记题干 |
| answer_imported | INFO | catalog | 导入的答案数。不记答案正文 |
| paper_created | INFO | practice | 学生卷标识 |
| page_stored | INFO | 文件适配器 | 文件标识 |
| analysis_finished | INFO | analysis | 任务标识、结果类别 |
| attempt_confirmed | INFO | practice | 确认记录标识 |
| log_failed | ERROR | 日志适配器 | 原来的 request_id。输出失败时留下这一条，不撤销已经完成的写入 |
| auth_denied | WARN | identity | 操作者标识、学生标识 |
| app_started / app_stopped | INFO | 组合根 | 无个人数据 |
| login_succeeded | INFO | identity | 操作者标识。不记口令，不记完整会话标识 |
| login_failed | WARN | identity | 错误码。不记用户名原文，不记口令 |
| session_revoked | INFO | identity | 操作者标识。不记完整会话标识 |
| admin_action_committed | INFO | identity | audit=true 时进入审计流。action、target_kind、target_id、outcome |
| audit_write_failed | ERROR | 审计 sink | 原来的 request_id。原事件另写入回退文件 |
| log_rotation | INFO | 文件 sink | 新文件的日期分段。不记日志正文 |
| webhook_failed | WARN | bootstrap | 原来的 request_id。不记地址，不记上报正文 |
