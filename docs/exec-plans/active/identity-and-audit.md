# 执行计划：登录、授权和审计落库

状态：进行中。2026-11-18。这一段把 `identity` 放进 `PHASE_SLICES`。`catalog` 和 `practice` 仍在。`knowledge`、`analysis`、`delivery` 仍不建目录。

有理数合成闭环的计划停在 [rational-number-loop.md](rational-number-loop.md)。那里的步骤不改。本文件只覆盖登录、老师与学生授权、审计和第一次 PostgreSQL 写入。

## 决定

- 角色只有 `admin` 和 `teacher`。会话在服务端。不使用 JWT、OAuth、SSO、密码找回、双因素或自助注册。
- 老师发卷仍走 practice 的 `Authorizer`。practice 不导入 identity。
- 持久化只有内存（测试和合成）和 PostgreSQL（真实）。不做 SQLite 过渡。
- 第一次有行要写的表是 users、sessions、students、teacher_grants、login_attempts、audit_events。题目表和答案表仍没有行，不在这次建。
- 运行日志和审计日志分开。运行日志默认保留 14 天。审计默认保留 5 年。

## 完成线

管理员能创建老师和学生、授予并撤销「老师-学生-学科」。老师登录后才能发卷。撤销后发卷被拒绝。审计行能被管理员读到。迁移在临时 PostgreSQL 里可以向前、回滚、再向前。

2026-11-18：登录页、老师页和管理页已接上。路径是 `/login`、`/` 和 `/admin`。

2026-11-18：本机 PostgreSQL 走查写在 `docs/evidence/identity-audit-2026-11-18.md`。默认进程仍不连接。外部 HTTPS、CORS、依赖扫描、SBOM、备份加密和 M-14 接收方仍未做。

2026-11-18：运行模式、会话清理、迁移锁、健康检查、首次改口令、读审计和最后一名管理员写在 ADR 0032 到 0038。catalog 与 practice 的落库写在 ADR 0039。这些决定的代码还没写。

## 还不做

学生账号、家长账号、安卓、题目表、答案表、对外错误上报的真实接收方。webhook 只留接口，默认关闭。
