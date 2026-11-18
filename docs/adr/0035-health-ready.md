# ADR 0035 存活和就绪

状态：accepted

## 背景

`GET /health` 只说明进程还在应答，正文只有 `status`。探针已经使用这条路径。真实老师的进程还要能单独回答数据库和迁移是否就绪。

## 选项

1. 把数据库检查放进现有的 `/health`。
2. 拆成存活和就绪。旧路径保持存活。

## 决定

选 2。

- `GET /health` 保持不变，等价于 `GET /health/live`。两者都不鉴权，成功时都是 200，正文 `{"status":"ok"}`。
- `GET /health/ready` 不鉴权。同时满足下面两点才是 200，正文 `{"status":"ok"}`：`SELECT 1` 成功；`schema_migrations` 里按 `applied_at` 最晚的一行等于进程发现的最高版本，且已应用版本集合与进程发现的版本集合相同。
- 否则 503，正文 `{"status":"unavailable"}`。`development` 且没有连接时也是 503。
- 同一 IP 每分钟超过 30 次返回 429，`code` 为已有的 `ip_throttled`。
- 正文不写连接串、口令、姓名或学号。

## 后果

现有探针继续打 `/health`。就绪失败不改变存活结果。本条不实现外部错误上报。

## 状态

采纳。2026-11-18。
