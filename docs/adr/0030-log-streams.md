# ADR 0030 运行日志和审计日志

状态：accepted

## 背景

ADR 0008 把日志定到标准输出。管理员还要能事后看到谁做了哪一次授权，并查看近期 ERROR。运行日志和审计日志的保留时间不同。ADR 0008 的正文不改。

## 选项

1. 所有事件继续只打到标准输出。
2. 两条流。运行日志走标准输出和可选的文件。审计日志走 `audit_events`。写审计失败时，运行流记 `audit_write_failed`，并把原事件追加到本地回退文件。

## 决定

选 2。

- `LogEvent` 增加 `actor_user_id`、`target_kind`、`target_id` 和 `audit`。`audit` 默认 false。旧的调用不传这些字段仍然合法。
- `CompositeLogger` 按 `event.audit` 分流。运行 sink 可以有多个。审计 sink 只有一个。
- 标准输出始终打开。文件 sink 由 `K12_LOG_FILE` 控制，默认 `1`。按日切分，单文件超过 50MB 再切。保留天数是 `K12_LOG_RETAIN_DAYS`，默认 14。轮转成功写 `log_rotation`。实现只用标准库，不导入 `logging`、`structlog` 或 `loguru`。
- 审计保留天数是 `K12_AUDIT_RETAIN_DAYS`，默认 1825（5 个 365 日）。
- 运行日志仍然不记明文口令、口令哈希、完整会话标识、CSRF 令牌、授权头、cookie、学生或老师的真实姓名、学号、整页照片和整段请求体。
- 审计可以记 `actor_user_id`、`target_kind`、`target_id`、`action` 和 `outcome`。同样不记明文口令或完整会话标识。
- 写用例成功时记一条 `audit=true` 的 `admin_action_committed`，`outcome=ok`。失败时同样记一条，`outcome=err`，并带 `reason_code`。
- `GET /api/admin/errors` 分页返回近 24 小时的 ERROR，仅管理员。webhook 由 `K12_ERROR_WEBHOOK_URL` 打开，默认空，空则不发送。
- 清理脚本 `scripts/retention_sweep.py` 按两个保留天数删除过期审计行和过期运行日志文件，并写 `log_retention_swept`。

## 后果

业务层仍只调用 kernel 的 Logger。具体文件和数据库写入在组合根的 sink 里。ADR 0008 的标准输出仍然保留。

## 状态

采纳。2026-11-18。不改 ADR 0008 正文。
