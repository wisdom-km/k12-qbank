# ADR 0031 网页路由

状态：accepted

## 背景

网页现在只有一个页面。登录、老师出卷和管理员后台需要不同的路径。ADR 0012 已经采纳 React。

## 选项

1. 用条件渲染切换画面，不增加路由包。
2. 增加 `react-router-dom`。许可证是 MIT。版本钉在 `apps/web/package-lock.json`。
3. 再引入第二套网页框架。

## 决定

选 2。

- 路径：`/login`、`/`（老师）、`/admin`。
- 进入受保护页面前先读 `GET /api/session`。未登录去 `/login`。
- 写请求带 `X-K12-CSRF`。401 时回到 `/login`。人已经在登录页时不再跳转。
- 老师页的 `teacher_id` 由服务端会话决定。页面不把操作者当作规则来源。
- 不并行引入第二套网页框架。
- 页面测试使用 vitest 和 jsdom。二者是开发依赖，许可证为 MIT，只为跑 B5 的四个页面用例。不进入 Python 进程。

## 后果

`apps/web` 增加上述依赖并更新锁文件。网页仍然只通过 HTTP 调用服务，不导入 `backend`。

## 状态

采纳。2026-11-18。用户已预批准 `react-router-dom`。vitest 和 jsdom 是这条测试要求带进来的开发依赖。
