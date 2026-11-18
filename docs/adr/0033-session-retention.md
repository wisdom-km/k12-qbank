# ADR 0033 会话和登录数据的清理

状态：accepted

## 背景

`sessions` 会过期，`login_attempts` 会堆积。停用或改口令之后，旧 cookie 不能继续用。学情三类记录的保留仍按 ADR 0020，本条不写那个天数，不填 DEC-03。不改 ADR 0020 和 ADR 0030 的正文。

## 选项

1. `expires_at` 一过就物理删除会话。
2. 过期先标吊销，保留一段时间再删。登录尝试按天数删除。停用、启用和重置口令的成功路径立即吊销该用户尚未过期的会话。

## 决定

选 2。`scripts/retention_sweep.py` 增加这两类扫描。每类成功写一条 `log_retention_swept`，字段里只记删除或标吊销的行数。

- `expires_at` 已过且 `revoked_at` 为空：把 `revoked_at` 写成当前时间。不在过期的同一秒删行。
- `revoked_at` 早于 `K12_SESSION_RETAIN_DAYS`（默认 30）天：物理删除该行。
- `login_attempts.attempted_at` 早于 `K12_LOGIN_ATTEMPT_RETAIN_DAYS`（默认 30）天：删除。
- 用例 `revoke_all_sessions_for(user_id)` 吊销该用户尚未过期的会话。`disable_teacher`、`enable_teacher` 和重置口令的成功路径各调用一次，并记 `session_revoked`，只记条数。失败路径不调用。
- 管理员路由 `POST /api/admin/users/{user_id}/sessions/revoke` 调用同一用例。管理员自己的会话也可以由此撤销。
- 不记完整会话标识，不记口令。审计保留天数仍是 1825。运行日志文件仍是 14 天。

## 后果

过期会话会先留下吊销时间，满保留天数才消失。停用老师时现有的吊销仍在，成功路径改走这一个用例，不另做第二套吊销。

## 状态

采纳。2026-11-18。不改 ADR 0020、ADR 0030 正文。
