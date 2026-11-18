# ADR 0036 首个管理员必须改口令

状态：accepted

## 背景

ADR 0026 用环境变量创建第一名管理员。这个口令来自启动配置，不能长期当作登录口令。不做密码找回邮件。不改 ADR 0026 的正文。

## 选项

1. 创建后即视为已改过口令。
2. 引导创建的那一名用户带「必须改口令」。登录后的会话只够改口令和离开。

## 决定

选 2。

- 迁移 `backend/identity/migrations/V003__must_change.sql` 给 `users` 增加 `must_change_password boolean NOT NULL DEFAULT false`。回滚文件删掉这一列。已有行保持 false。
- 只有 `bootstrap_admin` 创建的那一名用户写成 true。管理员稍后创建的老师仍是 false。
- 该用户登录仍得到服务端会话。标志为 true 时，只允许 `GET /api/session`、`POST /api/logout` 和 `POST /api/account/password`。其他请求返回 403，`code` 为 `password_change_required`。
- `POST /api/account/password` 成功后把标志改成 false。失败不改。
- 口令不进运行日志，也不进审计明细。

## 后果

引导口令只用于第一次登录。改完之前不能发卷，也不能调用管理接口。

## 状态

采纳。2026-11-18。不改 ADR 0026 正文。
