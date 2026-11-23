# 0.2.0 发布就绪回顾

日期：2026-11-23。基线是 `origin/main` `c62e439`（PR #77 的合并提交，2026-11-23T09:56:30Z）。这不是发布说明，不移动标签，不关 issue。

对账原文是 `docs/release/E1-release-readiness-2026-11-22.md`。那份清单的跟踪 issue 是 #71。E1 合入是 PR #69，合并提交 `c7b40d2`（2026-11-22T16:40:04Z）。下文「E1 之后」指 `c7b40d2` 之后、含 `c62e439` 的 `origin/main` 历史。

E1 原文已经声明做完、因此没有再列入剩余项的三件事：Actions 不再使用 Node 20，CI 产出 SBOM，生产 CORS 由 `K12_CORS_ORIGINS` 驱动。当时的 `deps-audit` 仍带 starlette waiver。waiver 的解除记在下面第 1 节。

记号：

- `[x]` 原文那一项已经落地
- `[~]` 做了一部分，原文的缺口还在
- `[ ]` 还没做
- `[—]` 范围变了，不再作为这一项

## 1. E1 原清单

13 条。`[x]` 2，`[~]` 0，`[ ]` 11，`[—]` 0。

### [x] starlette CVE waiver

PR #72，合并提交 `66587d3`。实现提交 `f887983` 把 fastapi 升到 0.165.0、starlette 升到 1.10.0；`0e78858` 去掉 7 个 PYSEC ignore；`873a4fd` 去掉 CI 里的到期日守卫。`requirements.txt` 现在是 `fastapi==0.165.0` 与 `starlette==1.10.0`。`.github/workflows/ci.yml` 里已经没有 `PYSEC-2026` 和 `--ignore-vuln`。两份 waiver 文档都写了 2026-11-23 解除。PR #72 的 `closingIssuesReferences` 是 #70，#70 已关闭。

这一项不再挡 0.2.0。

### [ ] M-14 外部错误上报

#47 仍是 OPEN。`backend/bootstrap/error_ring.py` 在 `K12_ERROR_WEBHOOK_URL` 为空时不发送，失败时写运行事件 `webhook_failed`。`docs/observability.md` 写明外部接收接口仍未对接，对外可访问之前不把 M-14 写成发布通过。E1 之后没有 PR 改这条。

#47 自己的完成标准是：有外部接收方，失败时本进程仍可继续，上报正文不含口令、会话、姓名、学号或整页照片。接收方不在本仓实现。

挡真实学生试用。不挡合成数据上的登录和出卷。相对「把已有内部标签再宣布成对外 0.2.0」，它仍是未完成项；#71 把它标成外部阻塞，不放进本仓必须再写一个功能的 A 清单。

### [ ] HTTPS 终结 / 反向代理

#28 仍是 OPEN。ADR 0040 写明 HTTPS 终结和反向代理不在那条 CORS 决定里。`docs/release/` 没有反向代理或证书配置。E1 原文把它留在 E2。

挡对外只经 HTTPS 提供教学服务。本机 `127.0.0.1` 上的合成 HTTP 仍在。不是当前 main 上缺一个已指定的补丁。

### [ ] 备份加密

#35 仍是 OPEN。完成标准是备份同时包含数据库和文件，并且离开本机前已加密。`docs/evidence/` 里能对上的演练记录仍是 `docs/evidence/backup-drill-2026-11-14.md`：两份临时文件，没有数据库转储。E1 原文把它留在 E2。

挡含学生照片和作答的备份离开本机。不挡合成数据上的 M1。

### [ ] 密钥轮换

没有单独 issue。E1 之后的代码里，`轮换` 只出现在运行日志按大小换文件（`backend/bootstrap/file_log.py`）和登录时更换会话 id（`backend/identity/application/login.py`）。这两处不是 E1 写的「密钥轮换」。`docs/release/` 没有轮换步骤。

E1 把它留在 E2。它挡的是密钥运维步骤还没写下来。不挡当前合成闭环。

### [ ] DEC-01 到 DEC-06

六条都还是未填。PRD 与 ADR 0010、ADR 0012 仍写本仓不代填。E1 之后没有提交填写这六条。

| 条 | 原文说它挡在什么之前 | 是本仓 0.2.0 代码 blocker 吗 |
| --- | --- | --- |
| DEC-01 | 用真实题页做之前 | 否。合成夹具不依赖它 |
| DEC-02 | 真实学生试用前 | 否。授权端口仍按已有代码工作 |
| DEC-03 | 真实学生试用前，也在调用真实模型之前 | 否 |
| DEC-04 | 真机验收前 | 否 |
| DEC-05 | 写达标之前。没有阈值就保持待验证 | 否 |
| DEC-06 | 试用反馈之后 | 否 |

### [ ] UI 原型 v2

E1 写它在 `D:\ui`，执行者是 UI 线，不在本仓。本仓 `apps/web` 的页面仍是登录、老师、管理和账户这条合成骨架。本回顾没有去 `D:\ui` 核对原型是否做完。范围没有改，所以不是 `[—]`。

不是本仓代码 blocker。

### [x] publication_asset / list publications

E1 当时的缺口是两句：资产表还没建，也没有列出出版物的接口。

- 列表：PR #75，合并提交 `ee8d282`。实现提交 `b860543`，契约提交 `8f08b03`。`GET /api/admin/publications`。无新迁移。成功读取不写审计（`backend/catalog/application/list_publications.py` 文件头）。PR 没有关闭 issue。
- 资产表：PR #76，合并提交 `2b9ffad`。实现提交 `8a8e6b8`，契约提交 `07fa6bb`。迁移 `V008__publication_asset.sql`。管理员路由是 `POST /api/admin/publications/{publication_id}/assets`、`DELETE .../assets/{publication_asset_id}`、`GET .../assets`。真正挂上写 `publication_asset_attached`，真正卸下写 `publication_asset_removed`。列出资产不写审计。PR 没有关闭 issue。

`docs/implementation-matrix.md` 2026-11-23 的 V008 那一行仍写：字节上传未做。那不在 E1 这条的「当前状态」原文里。字节上传另记在第 3 节，不把这条打成 `[~]`。

## 2. E1 之后新增的能力

`git log origin/main --merges c7b40d2..origin/main` 只有 4 个合并提交，按时间从早到晚如下。

### PR #72 E3 Part B

合并 `66587d3`（2026-11-22T17:45:27Z）。标题：升级 fastapi / starlette 清理 starlette CVE waiver。

- 对外能力：没有新路由。OpenAPI 里 `ValidationError` 的快照随 pydantic 2 重写，提交 `338250f`。依赖锁变成 fastapi 0.165.0、starlette 1.10.0，并钉住这次带进来的传递依赖。
- 迁移：无。
- 新审计 action：无。
- 关闭 issue：#70。

### PR #75 D8-B list publications

合并 `ee8d282`（2026-11-22T18:08:02Z）。

- 对外能力：`GET /api/admin/publications`。查询参数 `question_version_id`、`answer_version_id`、`subject_id`、`status`、`offset`、`limit` 都可选。`status` 只有 `active` 和 `retired`。排序只按 `publication_id`。路由第一句是 `admin_only`。
- 迁移：无。
- 新审计 action：无。这次读取不写审计。
- 关闭 issue：无。

### PR #76 D8-A publication_asset

合并 `2b9ffad`（2026-11-23T03:43:01Z）。

- 对外能力：按 `publication_id` 挂上、卸下、列出资产元数据。请求体是 `file_id`、`kind`、`checksum`、`size_bytes`、`mime_type`。没有上传字节的字段。路由第一句是 `admin_only`。
- 迁移：`V008`。
- 新审计 action：`publication_asset_attached`、`publication_asset_removed`。
- 关闭 issue：无。

### PR #77 #74 Part B

合并 `c62e439`（2026-11-23T09:56:30Z）。实现提交 `c73578c`，文档提交 `2e9bfd4`。

- 对外能力：没有新路由，OpenAPI 路径和字段没有为这一批改。同一 `question_version_id` + `answer_version_id` 可以留下多条 `retired`，同时至多一条 `active`。第二次 retire 不再因为旧的三列 UNIQUE 失败。响应仍是 `{"outcome": ...}`。
- 迁移：`V009`。删掉约束 `publication_binding_unique`，加上部分唯一索引 `publication_one_active`。
- 新审计 action：无。仍是 `publication_retired`。`target_id` 改为这次 `UPDATE ... RETURNING publication_id` 的那一行。
- 关闭 issue：#74。

这 4 个 PR 合计关闭的 issue 只有 #70 和 #74。

## 3. 当前已知债务

### 3.1 未关闭 issue

`gh issue list --state open` 在 2026-11-23 返回 13 条。分级只针对「要不要挡一份对外的 0.2.0」。已有标签 `v0.2.0` 指向 `925bc36`，CHANGELOG 写那一版不是对外发布。A 的标准是：不改代码或证据，就不能如实把当前 main 叫作对外 0.2.0。下面 13 条都不是这种缺口，所以 A 是 0。

| issue | 创建时要跟踪的事 | 现在仓库里能对上的事实 | 级 | 理由 |
| --- | --- | --- | --- | --- |
| #2 | M-10。安全基础 8 条只有条文，没有服务可以证明 | 服务、登录、参数化 SQL、argon2 已经在后续 PR 落地。issue 正文仍停在「运行时未实现」 | B | 建议做一次对照，把已有证据和仍缺的证据分开。不挡已打上的内部标签 |
| #3 | M-11。文件夹具演练过了，数据库和正式数据没恢复过 | 通过标准写的是题目进持久化之后做库加文件的同一次恢复。V004 已建 `questions`。`docs/evidence/backup-drill-2026-11-14.md` 仍是仅有的演练记录，没有数据库 | B | 演练还没做。#71 的 0.2.0 剩余清单没有这条。不做则 M-11 继续未满足 |
| #28 | 对外教学服务只经 HTTPS | 没有终结或反向代理配置。留 E2 | C | 挡真实对外入口。E1 已把它排出本仓当前批次 |
| #29 | 未登录不能读写真学情。当时参照实现写的是还没有 | CHANGELOG `0.2.0 — 2026-11-18` 已写会话 cookie `k12_sid` 和 `X-K12-CSRF`。标签 `925bc36` 是 PR #48 | B | 登录已经在那个标签里。issue 没关。建议核对完成标准后改写或关闭，不要把它写成「没有认证」 |
| #30 | 浏览器只接受点名的来源 | ADR 0040 已采纳。`K12_CORS_ORIGINS` 在 PR #69。issue 未关，AC-07 没有签收 | B | 控制已落地，跟踪票过期。关票不等于 AC 通过 |
| #31 | 超过约定上限的请求被拒绝，日志不记整段正文 | `backend/bootstrap/http_gate.py` 的 `_MAX_BODY` 是 1048576。带 `Content-Length: 2000000` 的登录请求在 `tests/test_http_session.py` 期望 413。没有 `Content-Length` 时 `_too_big` 直接返回假。引入这道检查的提交是 `ae54674` | B | 有代码上限，没有机构额度。无长度头的请求不由这道检查拒绝 |
| #32 | 同一来源超过约定次数时拒绝 | 登录：账号 5 次失败 / 15 分钟，IP 20 次 / 分钟（`memory_rate_limiter.py`）。`GET /health/ready`：同一 IP 每分钟超过 30 次返回 `ip_throttled`（ADR 0035）。不是每条路由都限额 | B | 有两处限额，没有一份覆盖全部入口的机构额度 |
| #33 | CI 能指出已知漏洞 | PR #69 加上 `deps-audit`，PR #72 去掉 waiver 后按失败退出。issue 未关 | B | 扫描已在 CI。跟踪票仍写「参照实现还没有」 |
| #34 | 发布物列出直接依赖的名称和版本 | `docs/evidence/sbom-2026-11-22.md`：CI 用 `cyclonedx-py` 产 `bom.json` 并上传，保留 90 天。issue 未关 | B | SBOM 已在 CI。issue 的完成标准还写「不把清单写成已经审计通过」 |
| #35 | 离开本机前的备份加密 | 见第 1 节。留 E2 | C | 挡真实学情备份离开本机。不挡合成 M1 |
| #47 | M-14 外部接收方 | 见第 1 节 | C | 挡真实学生试用。发送端已有，接收方在仓外 |
| #71 | 0.2.0 还不能当对外发布，并列出 E1 剩余项 | 正文仍写 waiver 未升、资产表留 D8。这两件已由 #72、#75、#76 落地 | B | 跟踪票过期。接受本回顾之后由人改写或关闭。本文件不关它 |
| #73 | starlette 1.10.0 下 `TestClient` 建议改用 `httpx2` | issue 写明只是警告，测试退出码 0，优先级低。`httpx2` 不在 `requirements.txt` | C | 不改变现有测试结果。等下一次 fastapi / starlette 升级再看它是否变成硬依赖 |

A 0 条，B 9 条（#2、#3、#29、#30、#31、#32、#33、#34、#71），C 4 条（#28、#35、#47、#73）。

### 3.2 代码内 TODO

在 `backend/` 与 `docs/` 搜索 `TODO`、`FIXME`、`XXX`，没有命中。

### 3.3 waiver 文档

`docs/release/E1-waiver-rationale-2026-11-22.md` 和 `docs/release/E1-waiver-review-2026-12-31.md` 都已写明 2026-11-23 解除，并指向 PR #72。CI 不再忽略那 7 个 id。两份文件是历史记录，可以归档。本批不移动、不删除。

### 3.4 ADR 里仍开着的决定

状态行是 `proposed` 的只有三条：ADR 0010（部署、安卓界面、供应商、备份数字仍有效；语言、网页框架、数据库产品已由 ADR 0012 取代）、ADR 0011（网页和桌面同一套界面）、ADR 0022（中文字体许可证；「等人决定字体」已由 ADR 0024 采纳，0022 正文不改）。没有 ADR 使用「待补充」这四个字。

正文里的「待定标」：

- ADR 0002：性能数字
- ADR 0008：日志保留期限
- ADR 0010：模型费用额度
- ADR 0020：备份窗口，并指向 DEC-03

这些都是 C。它们挡的是还没拍板的数字或产品形态，不挡当前合成服务的内部标签。

### 3.5 没有 issue 的后续

- 发布附件的字节上传和介质选型。main 上 `docs/implementation-matrix.md` 写「字节上传仍未做」。设计矩阵 `docs/design/D8-publication-asset-and-list-2026-11-23.md` 只在提交 `73828364`（分支 `chore/d8-design-matrix`），不在 main。C。
- 列表按数字序而不是 `publication_id` 字典序。PR #77 正文把它放在已知范围外，没有新 issue。C。本回顾不把它写成已排期。

## 4. 0.2.0 剩余清单

这里的「0.2.0」同时指两件已经分开的事：标签 `v0.2.0` 已经在 `925bc36`；issue #71 说这个版本号还不能当对外发布。

### A. 必须做（blocker）

无本仓功能 blocker。

不能据此宣布「当前 main 可以作为对外 0.2.0 发布」。标签已经指向更早的提交，见 C 节。真实学生试用仍被第 1 节里标成 E2、外部接收方和机构确认的那些 `[ ]` 挡住，那些放在第 3 节的 C，不放进 A。

### B. 建议做（nice-to-have）

1. 一个对账批次，只处理过期跟踪票：#29、#30、#31、#32、#33、#34、#71。每条按该 issue 自己的完成标准写「已落地的行为」和「仍不能签成 AC 通过的部分」。做了，开放列表就不再把 CORS、SBOM、依赖扫描和登录说成还没有。不做，功能不变，清单继续过期。不要在没核对完成标准时批量关闭。
2. 一个证据批次，对照 #2 和 #3。#2 把 8 条安全基础分成已有运行证据和仍没有的。#3 做一次数据库加文件的同一次恢复，并记下用时。做了，M-10 / M-11 的证据跟上 V004 之后的库。不做，这两条开工门继续未满足，合成登录和出卷仍可运行。
3. #73 不单开批次。并进下一次 fastapi / starlette 升级即可。现在不做，测试仍然是退出码 0 加一条弃用警告。

### C. 发布动作本身

- CHANGELOG 有一节 `## 0.2.0 — 2026-11-18`。内容停在身份、会话、`V001`，并写「这一版不是对外发布」。它没有描述 `c62e439` 上的题库表、发布账本、列表、资产或 V009。本批不改 CHANGELOG。
- 版本号：CHANGELOG 和标签是 0.2.0。`apps/web/package.json` 是 `0.1.0`。没有 Python 包版本字段需要一起改。本批不 bump。
- 标签：`v0.2.0` 是附注标签，对象 `5f77e6e2`，剥到提交 `925bc36`（PR #48，2026-11-18）。`draft-contract-1` 剥到 `9ed0d39`。两个标签都是 `origin/main` 的祖先。没有看到把标签挪到当前 main 的记录。
- GitHub Releases 列表为空。`docs/release/` 里没有发布说明模板，只有 E1 清单、两份 waiver 文档和本文件。

## 5. 推荐下一步

A 为空，B 不为空。推荐不要重发、也不要移动 `v0.2.0`。把 B 的两个批次排进下一次版本说明（用新的版本节，例如 0.2.1），C 留在那一版之外。

理由：`v0.2.0` 已经固定在 `925bc36`，CHANGELOG 写明那一版不是对外发布。E1 清单里本仓负责的两项，waiver 与发布列表加资产表，已经由 PR #72、#75、#76 落地。把 `c62e439` 再叫做 0.2.0 会覆盖那个已经存在的里程碑。B 只修正过期跟踪票和两份开工门证据，不改变对外契约。真实试用仍等 E2、外部接收方和 DEC，那些不是把当前 main 打上旧标签就能完成的。

本文件在分支 `chore/release-retro-2026-11-23`。按本批约定不开 PR。若要把它合进 main 供以后的发布说明引用，需要另一次决定。

## 6. E2、存储批次、前端

这三节只记事实，不排先后。

### E2

`docs/` 里有部署线索，没有选定的部署目标。

- ADR 0010 仍是 `proposed`。它把「机构电脑 + 手机可访问的受控局域网」写成默认计划，等 DEC-04 再采纳或替换。部署地点、安卓界面、模型供应商、备份数字没有被 ADR 0012 取代。
- ADR 0012 写部署地点不在那次技术栈决定里。
- 方案 1.1 第 10.1 节写老师可先在机构电脑部署，手机走受控局域网，并把上云时间、部署商、域名和预算写成尚未确定。
- `docs/release/` 没有主机名、证书、反向代理或 E2 执行计划。

### 设计矩阵里的下一次存储批次

矩阵没有使用「D8-C」这个名字。提交 `73828364` 写：D8-A 可以先登记合成的 `pubfile-` 标识；上传字节的 HTTP 和介质选型留给以后的存储批次；那一批才选介质。它没有写「等 E2 选定介质」。E1 清单里的 E2 是 HTTPS、备份加密和密钥轮换，和介质选型不是同一条。

main 上已经和这份矩阵不完全相同：PR #76 加了资产元数据的管理员路由和 `V008`。字节上传在 main 的实现矩阵里仍是未做。矩阵文件本身不在 main。

### 前端

`apps/web` 不是空目录。已跟踪的骨架包括 `package.json`（`0.1.0`）、`package-lock.json`、`index.html`、`vite.config.js`、`vitest.config.js`、`src/` 和 `tests/`。`src/` 里有 `main.jsx`、`routes.jsx`、`login_page.jsx`、`teacher_page.jsx`、`admin_page.jsx`、`account_page.jsx`，以及出卷循环、会话和 OpenAPI 生成类型。工作区里还有 `dist/` 和 `node_modules/`，本回顾不把它们当成发布物。
