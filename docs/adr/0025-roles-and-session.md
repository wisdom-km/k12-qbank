# ADR 0025 角色和会话

状态：accepted

## 背景

老师发卷现在靠组合根里的固定老师标识。机构管理员要能创建老师、创建学生，并维护老师、学生和学科的授权。页面不能自己挑选操作者。

## 选项

1. 继续用固定老师标识，管理功能以后再加。
2. 用 JWT、OAuth 或机构 SSO。
3. 服务端会话。角色只有 `admin` 和 `teacher`。浏览器只保存 HttpOnly cookie。

## 决定

选 3。

- 角色只有 `admin` 和 `teacher`。没有学生账号，没有家长账号，没有自助注册。
- 会话标识放在 cookie 里。属性是 HttpOnly、SameSite=Lax。`K12_SESSION_SECURE=1` 时加 Secure。本地 HTTP 默认是 `0`。
- 空闲 60 分钟，绝对 12 小时。环境变量 `K12_SESSION_IDLE_MINUTES` 和 `K12_SESSION_ABSOLUTE_HOURS` 可以覆盖。
- 登录成功发新的会话标识，并撤销该用户仍有效的旧会话。
- 非 GET 请求要带 `X-K12-CSRF`，值等于该会话的 CSRF 令牌。不等就 403。
- 不使用 JWT。不把会话标识放进前端可读的存储。
- practice 仍只调用 `Authorizer.allow`。它不导入 identity。组合根把授权结果装进这个端口。

## 后果

HTTP 入口从会话解出操作者，不再使用固定的 `ACTOR_TEACHER_ID`。未登录访问除 `GET /health` 和登录以外的接口，返回 401，正文不说明原因。

## 状态

采纳。2026-11-18。不改 R6 的原句。R6 的执行点仍是服务端用例。
