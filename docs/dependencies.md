# 锁定依赖

日期：2026-11-16。这一页记录已经锁进仓库的依赖，不新增包。运行依赖在仓库根的 `requirements.txt`，用 `==` 钉死。构建依赖在 `apps/web/package.json`，锁文件是 `apps/web/package-lock.json`。

名单以外的许可证标为待人审。这项决定不挡住其余合成路径上的修复。

## 运行依赖

这些包随合成 HTTP 进程安装。FastAPI 是 ADR 0012 已经采纳的网页框架。其余多为它和 uvicorn 带进来的传递依赖。标准库 `http.server` 能回一句健康检查，但不能替换已经采纳的框架。冒烟脚本本身用的是标准库 `urllib`。

| 包 | 版本 | 用途 | 许可证 | 更小的标准库做法 |
| --- | --- | --- | --- | --- |
| fastapi | 0.115.6 | 合成 HTTP 入口 | MIT | 已采纳，不用 `http.server` 替换 |
| starlette | 0.41.3 | FastAPI 的下层 | BSD-3-Clause | 同上 |
| uvicorn | 0.34.0 | 本机进程 | BSD-3-Clause | 同上 |
| pydantic | 2.14.3 | 请求体 | MIT | 手写解析能做这几个字段，但框架已经采纳 |
| pydantic_core | 2.50.4 | pydantic 的底层 | MIT | 同上 |
| annotated-types | 0.8.0 | pydantic 传递依赖 | MIT | 同上 |
| typing-inspection | 0.4.5 | pydantic 传递依赖 | MIT | 同上 |
| typing_extensions | 4.16.0 | 类型传递依赖 | PSF-2.0 | 3.12 已有一部分，这个钉死版本仍在锁里。PSF-2.0 不在 MIT、BSD、Apache-2.0 名单里，待人审 |
| anyio | 4.16.0 | Starlette 传递依赖 | MIT | 不单独调用 |
| click | 8.5.1 | uvicorn 传递依赖 | BSD-3-Clause | 不单独调用 |
| h11 | 0.16.0 | HTTP/1.1 解析 | MIT | 不单独调用 |
| idna | 3.20 | 主机名编码 | BSD-3-Clause | 不单独调用 |
| httpx | 0.28.1 | 测试客户端传递依赖 | BSD-3-Clause | 冒烟已经用 `urllib`。测试客户端仍需要它 |
| httpcore | 1.0.9 | httpx 传递依赖 | BSD-3-Clause | 同上 |
| certifi | 2026.10.23 | httpx 的证书包 | MPL-2.0 | 本机合成回环不发到外网。MPL-2.0 不在名单里，待人审。不因为这项停掉其余修复 |

## 构建依赖

只在构建网页时使用。构建结果是静态文件，由上面的 Python 进程送出。这些包不是 Python 运行时的一部分。

| 包 | 锁里的版本 | 用途 | 许可证 |
| --- | --- | --- | --- |
| react | 19.3.1 | 页面 | MIT |
| react-dom | 19.3.1 | 页面 | MIT |
| vite | 6.4.6 | 构建 | MIT |
| @vitejs/plugin-react | 4.7.0 | 构建 | MIT |

没有加入 reportlab 或 WeasyPrint。合成 PDF 仍由标准库写成一页 Helvetica，字体编码是 WinAnsi。

锁文件里还有这些构建期传递依赖。它们不进入 Python 进程。Apache-2.0 的 `baseline-browser-mapping` 和 BSD-3-Clause 的 `source-map-js` 在允许的许可证名单里。下面这些不在 MIT、BSD、Apache-2.0 名单里，待人审。这项决定不挡住其余修复，也没有为它增删包。

| 包 | 锁里的版本 | 用途 | 许可证 |
| --- | --- | --- | --- |
| caniuse-lite | 1.0.30001826 | `browserslist` 的浏览器数据。`@babel/helper-compilation-targets` 在构建时用它 | CC-BY-4.0，待人审 |
| electron-to-chromium | 1.5.486 | `browserslist` 把 Electron 版本对应到 Chromium。构建时使用 | ISC，待人审 |
| semver | 6.3.2 | Babel 编译目标比较版本。构建时使用 | ISC，待人审 |
| lru-cache | 5.1.1 | `@babel/helper-compilation-targets` 的缓存。构建时使用 | ISC，待人审 |
| yallist | 3.1.1 | `lru-cache` 的传递依赖。构建时使用 | ISC，待人审 |
| picocolors | 1.1.1 | Babel 和 Vite 在构建输出里上色。构建时使用 | ISC，待人审 |
