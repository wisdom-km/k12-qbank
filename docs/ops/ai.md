# AI 识别

识别分两步。转写只看照片和学生写的内容。判断才对照标准答案。选择题，以及填空里纯数字或纯字母的空，在本机比对，不发给模型。建议在老师确认之前不是结果。采用、修改、驳回是下一批。

默认适配器是 mock，不访问网络。要打到火山引擎方舟时，才按下面设置。密钥只留在这台机器上，不进仓库，不进日志，不进报错。

决定见 [ADR 0045](../adr/0045-ai-suggestions.md)。

## 从方舟控制台拿三样东西

用的是按量付费的 OpenAI 兼容接口，不是 Coding Plan。两套地址和密钥不能互换。Coding Plan 的地址是 `https://ark.cn-beijing.volces.com/api/coding/v3`，本服务不用它。

1. 打开火山方舟控制台（`https://console.volcengine.com/ark`）。登录的是机构账号。
2. 在 API Key 管理里创建或复制一把密钥。这是 `K12_AI_API_KEY`。页面上只显示一次的，当场抄到本机环境变量，不要贴进聊天、工单或仓库。
3. 模型 ID 或接入点 ID 二选一，填进 `K12_AI_MODEL`。模型广场里的模型 ID 是带日期的名字。在线推理里创建的接入点 ID 通常以 `ep-` 开头。控制台当天显示哪一个，就填哪一个。不要把某一个模型 ID 写进代码。
4. 接口地址填 `K12_AI_BASE_URL`。按量付费的兼容根路径是 `https://ark.cn-beijing.volces.com/api/v3`。接入点页面如果写了别的地域根路径，用页面上的那一个，不要自己改路径。程序会在这个根路径后面接 `chat/completions`。根路径如果已经以 `/chat/completions` 结尾，不会再接一次。

## 环境变量

只在启动这个进程的终端里设置，或写在本机不进仓库的环境里。`.env.example` 只有名字，值是空的。

```text
$env:K12_AI_PROVIDER = "volcengine"
$env:K12_AI_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
$env:K12_AI_MODEL = "<控制台上的模型 ID 或接入点 ID>"
$env:K12_AI_API_KEY = "<密钥>"
$env:K12_AI_TIMEOUT_SECONDS = "60"
$env:K12_AI_DAILY_LIMIT = "500"
```

`K12_AI_PROVIDER` 空着就是 mock。production 下选了 `volcengine`，但这三个里有空的：`K12_AI_BASE_URL`、`K12_AI_MODEL`、`K12_AI_API_KEY`，进程启动失败。标准错误里只有缺的变量名。

改完变量要重启进程。已经起来的进程不会重新读。

## 怎么运行 scripts/ai_probe.py

这个脚本只由人在本机手动运行。测试、CI 和 `scripts/check.ps1` 都不调用它。运行前先按上一节设好三个必填变量。脚本不打印密钥。

在仓库目录执行：

```text
python scripts/ai_probe.py
```

脚本先检查 `K12_AI_BASE_URL`、`K12_AI_MODEL`、`K12_AI_API_KEY` 都有值。缺了就打印 `缺少` 和变量名，退出码 2。

三个都有值时，它把本进程的 `K12_AI_PROVIDER` 设成 `volcengine`，发一条纯文字请求，正文要求对方返回 JSON。通过时打印：

```text
文字请求通过
耗时秒 0.000
input_tokens 0
output_tokens 0
```

耗时和 token 数是这一次的实测，上面的 `0` 只是格式。

可选参数 `--image` 再走一次转写。图片由运行的人自己提供，例如一张合成样卷的截图。不要把真实学生的整页照片放进仓库。

```text
python scripts/ai_probe.py --image path\to\page.jpg
```

转写通过时，在文字请求的输出之后再打印耗时、两侧 token，以及每题一行 JSON：`order_no`、`transcription`、`unreadable`、`confidence`。然后打印 `seen_page_no` 和 `seen_external_id_present`。后者只有 `yes` 或 `no`，不打印读到的学号原文。找不到文件时打印 `找不到图片`，退出码 2。

失败时只打印下面一类，退出码 1，不打印响应正文，不打印密钥：

| 打印 | 含义 |
| --- | --- |
| 地址不通 | 连不上 `K12_AI_BASE_URL`，或对方返回了除鉴权、模型不存在以外的 HTTP 错误 |
| 鉴权失败 | HTTP 401 或 403。密钥不对，或这把密钥不能用于这个地址 |
| 模型 ID 不对 | HTTP 404。`K12_AI_MODEL` 在这个地址上不存在 |
| 超时 | 在 `K12_AI_TIMEOUT_SECONDS`（默认 60）内没有完成。本机连不上一个关闭的端口时，也可能归到这一类 |
| 输出不合格 | 返回不是约定的 JSON，或转写结果缺字段。文字请求通过但正文不是 JSON 对象时，也打印这一句 |
| 未配置 | 三个变量在检查之后又变空。正常的缺变量会先走上面的退出码 2 |

真实调用会按方舟价目计费。没有必要不要反复跑 `--image`。

## 怎么切回 mock

```text
$env:K12_AI_PROVIDER = "mock"
```

或者从当前终端删掉 `K12_AI_PROVIDER`。然后重启进程。mock 不读密钥，也不访问网络。测试和 CI 保持这一档。

## 每日上限和超时

`K12_AI_DAILY_LIMIT` 默认 500。按 UTC 的日期计数，这一天里已经开始的识别都算，包括后来失败的。到了上限，新的开始返回 `ai_daily_limit`（HTTP 429），不插入新的运行记录。填 0 表示当天不能再开始。空或不是整数时用 500。

`K12_AI_TIMEOUT_SECONDS` 默认 60。空、不是整数或不大于 0 时用 60。超时只把这一次运行记成 `failed`，错误码 `timeout`。收卷和老师确认仍然可用。

同一张照片已有一次排队或进行中的识别时，再次开始返回 `ai_run_in_progress`（HTTP 409）。

## 大致费用

本批没有对真实接口跑过计费调用，下面不是实测账单。一次调用的费用大约是：输入 token 数乘以输入单价，加上输出 token 数乘以输出单价。token 数以该次响应里的 `usage` 为准。图片 token 怎么折算，以调用当天的方舟说明为准。路线图第 3 节有 2026-11-23 的摘录，那是当时的估算，不是本批的测量。

下面是在线推理（常规）公开价，单位是元 / 百万 token。来源是方舟模型价格页，页面更新时间 2026-11-24：

https://ark.volcengine.com/region:cn-beijing/docs/model-pricing.md

同一天读取到的区间和单价如下。区间写法保持该页原样，这里不换算单位。调用当天以控制台为准。

| 模型 | 输入长度区间 | 输入单价 | 输出单价 |
| --- | --- | --- | --- |
| doubao-seed-2.1-pro | [0, 1024] | 6.00 | 30.00 |
| doubao-seed-2.1-lite | [0, 1024] | 0.80（非音频） | 2.70 |
| doubao-seed-2.0-pro | [0, 32] | 3.2 | 16.0 |
| doubao-seed-2.0-lite | [0, 32] | 0.6（非音频） | 3.6 |

模型 ID 以 `K12_AI_MODEL` 为准。表里没有的模型，去同一页或控制台查，不要沿用上表。
