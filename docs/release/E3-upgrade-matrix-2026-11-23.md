# fastapi / starlette 升级矩阵

日期：2026-11-23。这不是升级，也不是试用，也不是 AC-01。

本批只读锁定、公告和源码。没有安装候选版本，没有改 `requirements.txt`，没有改业务代码或测试。基线是 `ce8a914`（分支 `chore/e1-supply-chain-hardening` 的 tip，本分支从这里拉出）。`requirements.txt` 相对 `origin/main` `d0d23d3` 没有 fastapi / starlette 行的差别。

PyPI 索引日是 2026-11-23。fastapi 的 `info.version` 是 `0.165.0`。没有 fastapi 1.x。

## 现状

`requirements.txt` 与 conda 环境 `k12-qbank` 的 `pip freeze` 这两行一致。解释器是 Python 3.12.16。

| 包 | requirements.txt | pip freeze | 行 |
| --- | --- | --- | --- |
| fastapi | 0.115.6 | 0.115.6 | `requirements.txt:8` |
| starlette | 0.41.3 | 0.41.3 | `requirements.txt:19` |
| pydantic | 2.14.3 | 2.14.3 | `requirements.txt:17` |
| pydantic_core | 2.50.4 | 2.50.4 | `requirements.txt:18` |
| uvicorn | 0.34.0 | 0.34.0 | `requirements.txt:23` |
| anyio | 4.16.0 | 4.16.0 | `requirements.txt:2` |
| httpx | 0.28.1 | 0.28.1 | `requirements.txt:11` |
| typing_extensions | 4.16.0 | 4.16.0 | `requirements.txt:21` |
| typing-inspection | 0.4.5 | 0.4.5 | `requirements.txt:20` |

`requirements.txt` 里 `fastapi==` 和 `starlette==` 各只有这一处。没有第二个包把它们锁在旧版本。传递依赖是顶层 `==`，不是「另一个发行包要求旧 starlette」。

## 七条 CVE

修复版本来自 OSV 的 `fixed` 事件（`https://api.osv.dev/v1/vulns/<GHSA>`，2026-11-23 读取）。GHSA API 的 `patched_versions` 是 null，同页给出 `vulnerable_version_range`。OSV 的 `fixed` 与 E1 基线 `docs/evidence/deps-audit-baseline-2026-11-22.md` 的 `fix_versions` 相同。不是从范围推出来的下一个版本号。

| id | GHSA | OSV fixed | 严重性（GHSA） |
| --- | --- | --- | --- |
| PYSEC-2026-1941 | [GHSA-2c2j-9gv5-cj73](https://github.com/advisories/GHSA-2c2j-9gv5-cj73) | 0.47.2 | medium。大文件 multipart 可能堵主线程 |
| PYSEC-2026-1942 | [GHSA-7f5h-v6xp-fcq8](https://github.com/advisories/GHSA-7f5h-v6xp-fcq8) | 0.49.1 | high。`FileResponse` 合并 Range 头 |
| PYSEC-2026-161 | [GHSA-86qp-5c8j-p5mr](https://github.com/advisories/GHSA-86qp-5c8j-p5mr) | 1.0.1 | medium。Host 头污染 `request.url.path` |
| PYSEC-2026-2281 | [GHSA-wqp7-x3pw-xc5r](https://github.com/advisories/GHSA-wqp7-x3pw-xc5r) | 1.1.0 | high。Windows 上 `StaticFiles` 的 UNC 路径 |
| PYSEC-2026-2280 | [GHSA-x746-7m8f-x49c](https://github.com/advisories/GHSA-x746-7m8f-x49c) | 1.1.0 | medium。`HTTPEndpoint` 用 `getattr` 派发任意方法 |
| PYSEC-2026-248 | [GHSA-jp82-jpqv-5vv3](https://github.com/advisories/GHSA-jp82-jpqv-5vv3) | 1.3.0 | low。请求路径拼进 authority，污染 `request.url.hostname` |
| PYSEC-2026-249 | [GHSA-82w8-qh3p-5jfq](https://github.com/advisories/GHSA-82w8-qh3p-5jfq) | 1.3.1 | high。`request.form()` 对 urlencoded 忽略大小限制 |

七条都清掉的最低 starlette 是 **1.3.1**。`starlette >= 0.47` 只盖住第一条。

本仓调用面：

- `request.form`、`UploadFile`、`Form(`、`HTTPEndpoint`：全库 `*.py` 无匹配。multipart 与 urlencoded form 这两条没有调用点。升级仍要换版本，pip-audit 才不再报。
- `FileResponse`：`backend/bootstrap/http_app.py:81`，`FileResponse(index)`，没有传已删除的 `method`。Range 合并那条会改恶意 Range 的行为。全库没有 `Range` 请求。
- `StaticFiles`：`backend/bootstrap/http_app.py:78`。全库没有 UNC 路径。
- `request.url.path`：`backend/bootstrap/http_gate.py:48` 和 `:52`。Host 污染修的是畸形 Host。TestClient 的正常 Host 不在这条的描述里。

## 候选组合

版本约束来自 PyPI `requires_dist` 与 `requires_python`。发布日是该版本文件的最早 `upload_time`。

### 任务里写的保守组合：做不到

fastapi 0.115 线的最后一版是 **0.115.14**（2025-06-26，Python `>=3.8`）。PyPI 声明：

`starlette<0.47.0,>=0.40.0`

`pydantic!=1.8,!=1.8.1,!=2.0.0,!=2.0.1,!=2.1.0,<3.0.0,>=1.7.4`

它装不上 starlette 0.47.2。当前 0.115.6（2024-12-03）更紧：`starlette<0.42.0,>=0.40.0`。

### 只盖住一部分的中间点

不建议为它们各开一批。每批都要重跑测试，而且 #70 仍然不能关。

| fastapi | 发布日 | starlette 声明 | 能钉的 starlette | 盖住的 fixed |
| --- | --- | --- | --- | --- |
| 0.116.1 | 2025-07-11 | `>=0.40.0,<0.48.0`，Python `>=3.8` | 0.47.2 | 只有 0.47.2 |
| 0.120.1 | 2025-10-27 | `>=0.40.0,<0.50.0`，Python `>=3.8` | 0.49.1 | 0.47.2 和 0.49.1 |
| 0.128.3 | 2026-02-06 | `>=0.40.0,<1.0.0`，Python `>=3.9`，`pydantic>=2.7.0` | 到不了 1.0.1 | 仍缺后五条 |

0.133.0（2026-02-24）把上限拿掉，声明改成 `starlette>=0.40.0`。这在字面上允许 1.3.1，但该版发布在 starlette 1.0.0（2026-03-22）之前。本批没有读 0.133.0 的源码，也没有安装。不把它写成可运行组合。

### 建议落地的组合

**fastapi 0.165.0**（2026-11-18）**+ starlette 1.10.0**（2026-10-24）。

PyPI：

- fastapi 0.165.0：Python `>=3.11`，`starlette>=1.6.0`，`pydantic>=2.9.0`，`anyio>=4.1.0`，`typing-extensions>=4.8.0`，`typing-inspection>=0.4.2`。uvicorn 只在 extra 里，`uvicorn[standard]>=0.12.0`。
- starlette 1.10.0：Python `>=3.11`，`anyio>=4.0.0,<5`。`httpx` 在 `full` extra：`httpx<0.29.0,>=0.27.0`，另有 `httpx2>=2.0.0`。

1.6.0 高于 1.3.1，所以这条 fastapi 声明允许的任何 starlette 都已经过了七条的 fixed。1.10.0 是索引日的最新 starlette。

本仓已有的版本落在这些声明里面：Python 3.12.16，pydantic 2.14.3，anyio 4.16.0，typing_extensions 4.16.0，typing-inspection 0.4.5，httpx 0.28.1，uvicorn 0.34.0。pydantic 不必跨大版本。pydantic 2.14.3 的 PyPI 声明把 `pydantic-core` 钉在 `==2.50.4`，与现在的锁定相同。

第一个把下限抬到 `starlette>=1.6.0` 的是 fastapi **0.164.0**（2026-11-18）。0.162.6（2026-11-13）仍是 `starlette>=0.46.0`、Python `>=3.11`、`pydantic>=2.9.0`。0.162.6 + starlette 1.3.1 在声明上合法，但本批没有读 0.162.6 的源码。不把它当作落地组合。

fastapi 1.x / 0.118 作为「最新激进线」：0.118 不是一条单独的产品线。最新发布就是 0.165.0。没有 1.x。

## 依赖会不会带着别的包走

- pydantic：0.128.0 的 Breaking Changes 原文是 “Drop support for `pydantic.v1`”。全库无 `pydantic.v1`。模型是 `pydantic.BaseModel`（`routes_admin.py:30` 起、`routes_session.py:22`、`routes_practice.py:19`、`routes_catalog.py:15`）。0.165.0 要 `pydantic>=2.9.0`。2.14.3 满足。不必升到索引上的 2.14.4。
- uvicorn：fastapi 没有把它列为硬依赖。声明的最低仍是 extra `>=0.12.0`。0.34.0 满足这条声明。本批没有拿 uvicorn 0.34.0 去加载 starlette 1.10。索引上的最新 uvicorn 是 0.54.0，没有取到它的 `requires_dist`（请求 TLS 中断）。不把 0.54.0 写成必须。
- anyio：starlette 1.7.0 Changed 原文是 “Require `anyio>=4.0.0,<5`”。0.165.0 再要 `anyio>=4.1.0`。4.16.0 两边都满足。
- httpx：TestClient 会 import 它。1.10.0 的 full extra 接受 `httpx<0.29.0,>=0.27.0`。0.28.1 在这个区间里。不要为了 extra 去装 `httpx2`。
- 其他锁定行：Part B 若只升 fastapi 与 starlette，安装器可能改掉别的传递锁定。那时候用干净虚拟环境的 `pip freeze` 对账，只提交真正变化的 `==` 行。本批没有做这次安装，所以不能列出那些行。

## changelog 里的破坏条目

fastapi 文本：`docs/en/docs/release-notes.md`，tag 以仓库 `master` 为准，摘的是 0.115.6 之后、标题含 Breaking 或 Deprecat 的小节。共 19 节。

starlette 文本：`docs/release-notes.md`。从 0.41.3 到 1.10.0，小节标题是 Added / Changed / Fixed / Removed / Deprecated，没有名为 Breaking 的小节。下面按 Removed 与 Deprecated 逐条记。Changed 只记和本仓调用相交的那一条。

命中是指本仓 `*.py` 有对应调用。成本只评「要不要改本仓代码」。未安装，所以成本不是测试结果。

### 命中

| 来源 | 原文 | 命中 | 成本 |
| --- | --- | --- | --- |
| starlette 1.0.0rc1 Removed | Remove `@app.middleware()` decorator from `Starlette`. Use `middleware` parameter instead | `backend/bootstrap/http_app.py:118` `@app.middleware("http")` | 低。Starlette 1.10.0 的 `starlette/applications.py` 已没有这个方法，只剩 `add_middleware`。fastapi 0.165.0 的 `fastapi/applications.py` 自己仍定义 `middleware`，函数体是 `self.add_middleware(BaseHTTPMiddleware, dispatch=func)`。沿用 0.165.0 时这一行不用改。若选一个没把该方法补回去的 fastapi，这一条变成要改中间件的注册方式 |
| fastapi 0.132.0 Breaking Changes | Now FastAPI checks, by default, that JSON requests have a `Content-Type` header with a valid JSON value, like `application/json`, and rejects requests that don't | 页面 `apps/web/src/auth.js:71` 与 `apps/web/src/api.js:3` 已发送 `Content-Type: application/json`。测试 POST 使用 TestClient 的 `json=` | 低。现有业务调用已经带头。`tests/test_http_session.py:71` 用 `content=b"{}"` 且不带头，但 `http_app.py:124` 先跑 `gate`，`http_gate.py:60` 按 Content-Length 拒绝，`http_errors.py:28` 把它收成 413。这条请求到不了路由上的 content-type 检查。Part B 仍要复跑这一条，确认 413 还在 |
| starlette 0.49.0 Changed | Do not pollute exception context in `Middleware` when using `BaseHTTPMiddleware` | `http_app.py:126` 的 `except Exception` 包住 `call_next`。0.165.0 的装饰器内部就是 `BaseHTTPMiddleware` | 低。没有新的调用要写。异常时本仓返回 JSON 500。Part B 复跑会打到这条 `except` 的 HTTP 测试 |

命中合计：低 3，中 0，高 0。

### fastapi Breaking / Deprecat，未命中

| 版本 | 原文要点 | 判定 |
| --- | --- | --- |
| 0.162.6 | Drop support for Python 3.10 | 未命中。本机是 3.12.16。0.165.0 要 `>=3.11`，3.12.16 满足 |
| 0.162.0 | Restore default handling for omitted boolean form fields | 未命中。无 `Form(` |
| 0.160.0 | Apply each parameter model's `extra` configuration to sibling fields | 未命中。模型没有 `model_config` 的 extra |
| 0.155.0 | Remove deprecated `**extra` from request parameters | 未命中。路由参数没有 `**extra` |
| 0.151.0 | Distinguish JSON null from omitted body values | 未观察到调用。`PublishPublicationBody.layout_template_id` 在 `routes_admin.py:59` 是 `str | None = None`。测试没有发送 JSON null。不把这一条记成已经要改的行 |
| 0.150.0 | Treat unselected browser file inputs as missing | 未命中。无文件表单 |
| 0.149.0 | Treat empty scalar values as missing in form models | 未命中。无 form model |
| 0.148.0 | Fix default handling for request parameters and models | 原文没有列出被改掉的签名。本仓 body 是必填 `str` 加少量默认值。未安装，不能指到一个会变的行 |
| 0.147.0 | Treat omitted boolean form fields as False | 未命中。无 form |
| 0.146.0 | Deprecate the `root_path` parameter in `FastAPI` | 未命中。`FastAPI(...)` 只传 `title` 和文档开关，`http_app.py:113-114` |
| 0.145.0 | Remove deprecated `openapi_prefix` and unused `**extra` from `FastAPI` | 未命中。无 `openapi_prefix` |
| 0.143.0 | Require opt-in for automatic OpenTelemetry exporter setup | 未命中。无 OpenTelemetry 调用 |
| 0.137.0 | `router.routes` is no longer a plain list of `APIRoute` objects | 未命中。全库没有读取 `router.routes` / `app.routes` |
| 0.131.0 | Deprecate `ORJSONResponse` and `UJSONResponse` | 未命中 |
| 0.129.0 | Drop support for Python 3.9 | 未命中。同 0.162.6 |
| 0.128.0 | Drop support for `pydantic.v1` | 未命中。无 `pydantic.v1` |
| 0.127.0 | Add deprecation warnings when using `pydantic.v1` | 未命中 |
| 0.125.0 | Drop support for Python 3.8 | 未命中 |

### starlette Removed / Deprecated，未命中

| 版本 | 原文要点 | 判定 |
| --- | --- | --- |
| 1.10.0 Deprecated | Deprecate `starlette.formparsers.FormMessage` | 未命中 |
| 1.0.0rc1 Removed | Remove `on_startup` / `on_shutdown` parameters | 未命中。无 `on_startup` |
| 1.0.0rc1 Removed | Remove `on_event()` decorator | 未命中。无 `on_event`。fastapi 0.165.0 仍保留一个会转调 `router.on_event` 的弃用方法；本仓不调用它 |
| 1.0.0rc1 Removed | Remove `add_event_handler()` | 未命中 |
| 1.0.0rc1 Removed | Remove `startup()` / `shutdown()` on `Router` | 未命中 |
| 1.0.0rc1 Removed | Remove `@app.route()` | 未命中。路由用的是 `@app.get` / `@app.post` |
| 1.0.0rc1 Removed | Remove `@app.websocket_route()` | 未命中 |
| 1.0.0rc1 Removed | Remove `@app.exception_handler()` | 未命中。无 `exception_handler` |
| 1.0.0rc1 Removed | Remove `iscoroutinefunction_or_partial()` | 未命中 |
| 1.0.0rc1 Removed | Remove `**env_options` from `Jinja2Templates` | 未命中 |
| 1.0.0rc1 Removed | Remove deprecated `TemplateResponse(name, context)` | 未命中 |
| 1.0.0rc1 Removed | Remove deprecated `method` parameter from `FileResponse` | 未命中。`http_app.py:81` 只传路径 |
| 0.50.0 Removed | Drop Python 3.9 support | 未命中 |
| 0.46.0 Deprecated | Add deprecated warning to `TestClient(timeout=...)` | 未命中。`TestClient(` 都没有 `timeout=`。`timeout=` 出现在 `subprocess` 和 socket 上 |
| 0.45.0 Removed | Drop Python 3.8 support | 未命中 |
| 0.45.0 Removed | Remove `ExceptionMiddleware` import proxy | 未命中 |
| 0.45.0 Removed | Remove deprecated `WS_1004_NO_STATUS_RCVD` and `WS_1005_ABNORMAL_CLOSURE` | 未命中 |
| 0.43.0 Removed | Remove deprecated `allow_redirects` argument from `TestClient` | 未命中 |

starlette 1.8.0 Changed 要求 Python 3.11+。3.12.16 满足，不单列成代码命中。1.7.0 把 `CORSMiddleware` 的注解放宽到 `Collection[str]`。`http_app.py:181-184` 传入的是 `list`，注解放宽不要求改调用。

### 任务点名、上面没有单独成行的几项

- `BackgroundTasks` / `Depends`：全库无匹配。
- 异常处理器签名：全库无 `exception_handler`。没有要改的签名。
- `startup` / `shutdown` 迁到 lifespan：本仓没有注册 startup。TestClient 用 `with`，走的是默认 lifespan。没有 `on_event` 要迁。
- OpenAPI：Breaking 小节里没有「schema 形状变了」这一句。0.145.0 删的是 `openapi_prefix`，本仓不用。开关仍是 `http_app.py:111-114` 的 `docs_url` / `redoc_url` / `openapi_url`。`scripts/check.ps1:248-257` 只在 `-Ci` 时导出并 `git diff` `api.openapi.json`，再核对 `api.types.ts`。CI 跑的是 `bash scripts/check --ci`（`.github/workflows/ci.yml` 的 check 作业）。schema 字节若变，这一步会红。那是生成文件要重跑脚本，不是手改。本批没有导出，所以不知道字节会不会变。
- `scripts/check.ps1` 不写死 fastapi 版本。它检查 `requirements.txt` 是否全 `==`。升级后仍然要全 `==`。脚本本身不用为版本号改。

## 测试

383 这个数字来自 `ce8a914` 上的 `python -m unittest discover -s tests -v`（无库 383，skipped=94；`k12_d5_schema` 383）。本批没有在新版本上重跑。

最可能先红的是用了 `TestClient` 的模块，因为中间件、lifespan 和 content-type 都从这里进：

- `tests/test_http_session.py`
- `tests/test_http_cors.py`
- `tests/test_http_loop.py`
- `tests/test_http_publication_publish.py`
- `tests/test_http_publication_retire.py`
- `tests/test_health_ready.py`
- `tests/test_openapi_hidden.py`
- `tests/test_must_change.py`
- `tests/test_session_revoke.py`
- `tests/test_m1_review.py`
- `tests/http_client.py`（被别的测试当客户端）

建议的 smoke，按这个顺序，红了就停：

1. `python -m unittest tests.test_run_mode tests.test_http_cors tests.test_http_session tests.test_openapi_hidden tests.test_health_ready -v`
2. 上面列出的其余 `test_http_*` 与 publication HTTP 模块
3. `python -m unittest discover -s tests -v`（先无 `K12_PG_DSN`，再一次性库）
4. `scripts/check.ps1`，以及 CI 上的 `bash scripts/check --ci`

`scripts/check.ps1` 不需要为这次升级改流程。`-Ci` 的 OpenAPI 对账要留着。

## 分批

不要拆成 0.47、再 0.49、再 1.3。那三跳都盖不住 #70，却各要一轮 383。

**Part B。** 在 #69 合入之后做。只动锁定和 waiver 所在的 CI 忽略列表：fastapi 0.165.0，starlette 1.10.0，pydantic 保持 2.14.3，uvicorn 保持 0.34.0，除非干净环境的安装器证明某条传递锁定必须变。不预先改 `http_app.py`。跑上面的 smoke，再跑全量。全绿之后，同一批删掉 deps-audit 里那 7 个 `--ignore-vuln`。七条的 fixed 都被 1.10.0 盖住，这一批就可以解除 waiver 并关闭 #70。

G2 在 Part B 才会动：M-06 与 M-08 必须重跑；M-09 仍要求全 `==`；M-13 仍是不发布；M-14 仍是未通过。切片实现程度不变。

**Part C。** 只有 Part B 的测试或 `--ci` 的 OpenAPI diff 变红才开。改动限在失败断言指向的文件。预期落点是 `http_app.py` 的中间件，或 `tests/test_http_session.py:71` 的 413，或导出的 `api.openapi.json`。不要在测试还绿的时候改这些文件。Part C 若发生，#70 留到 Part C 全绿再关。

本批估计：#70 在 Part B 之后关闭。这是估计。新版本没有装过，也没有跑过 383。

## 自审

- [x] 没有手改生成文件。没有跑 `export_openapi.py`。
- [x] Breaking / Removed / Deprecated 的句子来自上述两份 release notes，并带了版本号。
- [x] fixed 版本来自 OSV 的 `fixed` 事件，并与 E1 基线表一致。GHSA 的 `patched_versions` 是 null，没有拿它填版本号。
- [x] 成本旁边都有本仓路径，或者写明全库无匹配。没有把未安装的组合写成已经能跑。
- [x] 没有学号、姓名或真实业务数据。
- [x] 没有改 R1–R6 的边界，也没有改代码。
