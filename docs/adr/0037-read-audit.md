# ADR 0037 读审计

状态：accepted

## 背景

ADR 0030 在写用例成功或失败时记 `admin_action_committed`。管理员打开审计列表或近期错误时，这次读取本身也要留下记录。不改 ADR 0030 的正文。

## 选项

1. 读取不记审计。
2. 管理员校验通过后的读取记一条，明细不含结果。

## 决定

选 2。

- `GET /api/admin/audit` 和 `GET /api/admin/errors` 在校验通过并开始读取时，各写一条 `audit=true` 的事件。动作是 `admin_read_committed`，`outcome` 为 `ok`。
- `target_kind` 分别是 `audit` 和 `errors`。
- `detail_json` 只记 `limit`、`offset`，以及本次出现过的筛选字段名。不记筛选值，不记结果行。
- 未登录或非管理员的拒绝不写这一条。写审计失败时仍走 ADR 0030 已有的 `audit_write_failed`，不另做一条失败策略。
- 不记口令、口令哈希或完整会话标识。

## 后果

审计列表会因此多出读取记录。分页参数的值不进入明细，避免把查询内容复制进审计。

## 状态

采纳。2026-11-18。不改 ADR 0030 正文。
