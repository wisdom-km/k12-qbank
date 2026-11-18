# 健康检查与错误上报

状态：本机合成 HTTP 有 `GET /health`。正文仍只有 `status`。没有数据库检查。错误上报接收接口还没有。对外可访问之前，不把 M-14 写成发布通过。

## 健康检查

有服务端之后，HTTP 入口提供 `GET /health`。

进程能应答时，正文只有：

```json
{"status": "ok"}
```

返回里不放密钥、连接串、数据库地址、学生标识、姓名或照片。

`backend/bootstrap/health.py` 的 `health_report()` 返回这个固定状态。`GET /health` 原样返回它，不检查数据库。数据库出现之后，同一个接口再回答「必需依赖是否可连」。连不上就不是 `ok`。

运行平台可以用这个接口决定要不要重启。返回里仍然不放内部细节。

## 错误上报

网页和以后的安卓客户端把错误发到我们自己的接口。老师在界面上看到错误编号。上报里带同一个编号，才能和日志对上。

最小字段：

| 字段 | 含义 |
| --- | --- |
| error_id | 界面上给老师看的错误编号 |
| request_id | 和服务端日志里的请求编号相同 |
| app_version | 客户端版本 |
| platform | `web` 或 `android` |
| error_code | 稳定错误码，不是堆栈原文 |

样例：

```json
{
  "error_id": "err-synth-1",
  "request_id": "req-synth-1",
  "app_version": "0.0.0",
  "platform": "web",
  "error_code": "store_failed"
}
```

不上报这些内容：学生照片、姓名、学号、整页或裁切后的图片、密钥、token、连接串、整段请求体、完整提示词。堆栈若要留下，先去掉这些内容。

管理员只读接口 `GET /api/admin/errors` 返回近 24 小时的 ERROR。webhook 由 `K12_ERROR_WEBHOOK_URL` 打开，默认空，空则不向外发送。网页只在页面上显示拒绝码，不把学号或请求体送去上报。

## 现在不做

不接第三方崩溃服务。不把本机健康应答写成对外发布已通过。不把 `status=ok` 写成数据库已就绪。
