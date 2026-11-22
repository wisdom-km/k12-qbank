# ADR 0040 生产 CORS 白名单由 K12_CORS_ORIGINS 驱动

状态：accepted

## 背景

网页开发服务器在 `http://127.0.0.1:5173` 和 `http://localhost:5173`。接口进程另开端口。浏览器跨源请求要有 CORS。此前 `backend/bootstrap/http_app.py` 没有 `CORSMiddleware`。生产不能把来源默认成 `*`，尤其是凭证打开的时候。不改 ADR 0032 的正文。

## 选项

1. 不启 CORS。开发服务器继续用同源代理。生产由反向代理处理，本进程不表态。
2. 启用 `CORSMiddleware`。`K12_CORS_ORIGINS` 是逗号分隔的来源。`development` 未设置时用上面两个本地地址。`production` 未设置或清空后没有来源就退出。名单里出现 `*` 也退出。

## 决定

选 2。组合根在连接数据库之前检查。

- `allow_credentials` 为真。
- `allow_methods` 只保留路由上已经有的 `GET` 和 `POST`。
- `allow_headers` 只保留网页已经发送的 `Accept`、`Content-Type`、`X-K12-CSRF`。
- 不写 `*`。空名单也不改写成 `*`。
- 拒绝时标准输出一条 ERROR，`event` 是 `startup_refused`，进程退出码 1。来源字符串和连接串都不写入这条日志。

## 后果

`development` 且未设置 `K12_CORS_ORIGINS` 时，现有不带 `Origin` 的测试行为不变，也不多一条启动日志。`production` 必须给出名单，否则进程起不来。HTTPS 终结和反向代理仍不在本决定里。

## 状态

采纳。2026-11-22。不改 ADR 0032 正文。
