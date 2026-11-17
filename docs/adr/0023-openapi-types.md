# ADR 0023 用 OpenAPI 生成网页类型

状态：accepted

## 背景

合成 HTTP 用 FastAPI。默认进程把 `docs_url`、`redoc_url`、`openapi_url` 都设成没有，页面不公开接口文档。

网页现在是 JSX。有一项要求用 `openapi-typescript` 生成 `apps/web/src/api.types.ts`，并且 CI 核对这个文件和导出的 schema 一致。

`openapi-typescript` 7.13.0 的许可证是 MIT。MIT 在允许名单里。

## 选项

1. 默认进程打开 `/docs` 和 `/openapi.json`，再生成类型。
2. 默认进程保持关闭。只有导出脚本在内存里要一份 schema，不监听端口。类型文件提交进仓库，CI 重新生成后做对比。

## 决定

选 2。同一改动里加入 ADR 和开发依赖 `openapi-typescript` 7.13.0。它只在生成类型时使用，不进页面运行。

`create_app()` 默认仍关闭 OpenAPI。`openapi=True` 只给 `scripts/export_openapi.py` 和 `scripts/check_api_types.py`。这两个脚本不启动服务。

核对页仍占用 8765 时，不在本机跑会启动教学服务的全量检查。

## 后果

`apps/web/src/api.types.ts` 必须和导出结果一致。CI 的 `check` 在安装锁文件之后运行 `python scripts/check_api_types.py`。没有给这个作业加 `if:`。页面还没有改成 TypeScript，这个文件先只作核对。

## 状态

采纳。2026-11-18。许可证是 MIT，和生成文件放在同一改动里。默认进程不打开 OpenAPI。
